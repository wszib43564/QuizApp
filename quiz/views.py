import math
import secrets
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from .forms import FormularzAdresuWysylki, FormularzLogowania, FormularzRejestracji
from .models import Answer, PointTransaction, Question, Quiz, QuizAttempt, Reward, RewardRedemption, UserProfile


def _pozostaly_czas_quizu(podejscie):
    minelo = (timezone.now() - podejscie.started_at).total_seconds()
    return max(0, math.ceil(podejscie.quiz.time_limit_seconds - minelo))


def _zakoncz(podejscie, powod):
    with transaction.atomic():
        podejscie = QuizAttempt.objects.select_for_update().select_related("quiz", "user").get(id=podejscie.id)
        if podejscie.completed_at:
            return podejscie
        if powod == "QUIZ_TIMEOUT":
            odpowiedziane = podejscie.correct_answers + podejscie.incorrect_answers
            podejscie.incorrect_answers += max(0, podejscie.total_questions - odpowiedziane)
        wynik = podejscie.correct_answers * 10 - podejscie.incorrect_answers * 5
        podejscie.point_score = wynik
        if podejscie.is_rewarded_attempt:
            profil, _ = UserProfile.objects.get_or_create(user=podejscie.user)
            profil = UserProfile.objects.select_for_update().get(id=profil.id)
            stare = profil.points
            profil.points = max(0, profil.points + wynik)
            profil.save(update_fields=["points"])
            podejscie.balance_change = profil.points - stare
            PointTransaction.objects.create(user=podejscie.user, points=podejscie.balance_change, transaction_type="quiz", description="Quiz: " + podejscie.quiz.title)
        podejscie.finish_reason = powod
        podejscie.completed_at = timezone.now()
        podejscie.save()
        return podejscie


def strona_glowna(request):
    kontekst = {}
    if request.user.is_authenticated:
        profil, _ = UserProfile.objects.get_or_create(user=request.user)
        kontekst["profil"] = profil
    return render(request, "quiz/home.html", kontekst)


def rejestracja(request):
    if request.user.is_authenticated: return redirect("strona_glowna")
    if request.method == "POST":
        formularz = FormularzRejestracji(request.POST)
        if formularz.is_valid():
            u = formularz.save(); UserProfile.objects.create(user=u); login(request, u); return redirect("strona_glowna")
    else: formularz = FormularzRejestracji()
    return render(request, "quiz/register.html", {"formularz": formularz})


def logowanie(request):
    if request.user.is_authenticated: return redirect("strona_glowna")
    if request.method == "POST":
        formularz = FormularzLogowania(request, data=request.POST)
        if formularz.is_valid(): login(request, formularz.get_user()); return redirect("strona_glowna")
    else: formularz = FormularzLogowania()
    return render(request, "quiz/login.html", {"formularz": formularz})


@require_POST
def wylogowanie(request): logout(request); return redirect("strona_glowna")


@login_required(login_url="logowanie")
def lista_quizow(request):
    elementy = []
    for quiz in Quiz.objects.filter(is_active=True).order_by("title"):
        aktywne = QuizAttempt.objects.filter(user=request.user, quiz=quiz, completed_at__isnull=True).first()
        punktowane = aktywne.is_rewarded_attempt if aktywne else not QuizAttempt.objects.filter(user=request.user, quiz=quiz, is_rewarded_attempt=True).exists()
        elementy.append({"quiz": quiz, "ma_aktywne_podejscie": bool(aktywne), "bedzie_punktowane": punktowane})
    return render(request, "quiz/quiz_list.html", {"elementy_quizow": elementy})


@login_required(login_url="logowanie")
@require_POST
def rozpocznij_quiz(request, id_quizu):
    quiz = get_object_or_404(Quiz, id=id_quizu, is_active=True)
    liczba = quiz.question_set.count()
    if not liczba:
        messages.error(request, "Ten quiz nie posiada jeszcze pytań."); return redirect("lista_quizow")
    aktywne = QuizAttempt.objects.filter(user=request.user, quiz=quiz, completed_at__isnull=True).first()
    if aktywne:
        podejscie = aktywne
    else:
        bylo = QuizAttempt.objects.filter(user=request.user, quiz=quiz, is_rewarded_attempt=True).exists()
        podejscie = QuizAttempt.objects.create(user=request.user, quiz=quiz, total_questions=liczba, is_rewarded_attempt=not bylo)
        request.session[f"podejscie_{podejscie.id}_index"] = 0
        request.session[f"podejscie_{podejscie.id}_question_started"] = timezone.now().timestamp()
    request.session[f"quiz_{quiz.id}_attempt"] = podejscie.id
    return redirect("pytanie_quizu", id_quizu=quiz.id)


@login_required(login_url="logowanie")
def pytanie_quizu(request, id_quizu):
    quiz = get_object_or_404(Quiz, id=id_quizu, is_active=True)
    id_podejscia = request.session.get(f"quiz_{quiz.id}_attempt")
    podejscie = get_object_or_404(QuizAttempt, id=id_podejscia, user=request.user, quiz=quiz, completed_at__isnull=True)
    if _pozostaly_czas_quizu(podejscie) <= 0:
        podejscie = _zakoncz(podejscie, "QUIZ_TIMEOUT")
        return redirect("wynik_quizu", id_quizu=quiz.id, id_podejscia=podejscie.id)
    pytania = list(Question.objects.filter(quiz=quiz).order_by("order", "id"))
    indeks = request.session.get(f"podejscie_{podejscie.id}_index", 0)
    if indeks >= len(pytania):
        podejscie = _zakoncz(podejscie, "COMPLETED")
        return redirect("wynik_quizu", id_quizu=quiz.id, id_podejscia=podejscie.id)
    pytanie = pytania[indeks]
    start_pytania = request.session.get(f"podejscie_{podejscie.id}_question_started", timezone.now().timestamp())
    pozostalo_pytanie = max(0, math.ceil(pytanie.time_limit_seconds - (timezone.now().timestamp() - start_pytania)))
    if request.method == "POST":
        timeout = request.POST.get("timeout") == "1" or pozostalo_pytanie <= 0
        poprawna = False
        if not timeout:
            odpowiedz = get_object_or_404(Answer, id=request.POST.get("odpowiedz"), question=pytanie)
            poprawna = odpowiedz.is_correct
        if poprawna: podejscie.correct_answers += 1
        else: podejscie.incorrect_answers += 1
        podejscie.save(update_fields=["correct_answers", "incorrect_answers"])
        request.session[f"podejscie_{podejscie.id}_index"] = indeks + 1
        request.session[f"podejscie_{podejscie.id}_question_started"] = timezone.now().timestamp()
        return redirect("pytanie_quizu", id_quizu=quiz.id)
    return render(request, "quiz/quiz_question.html", {"quiz": quiz, "pytanie": pytanie, "numer": indeks + 1, "liczba_pytan": len(pytania), "pozostaly_czas_quizu": _pozostaly_czas_quizu(podejscie), "pozostaly_czas_pytania": pozostalo_pytanie, "podejscie": podejscie})


@login_required(login_url="logowanie")
def wynik_quizu(request, id_quizu, id_podejscia):
    podejscie = get_object_or_404(QuizAttempt, id=id_podejscia, quiz_id=id_quizu, user=request.user)
    return render(request, "quiz/quiz_result.html", {"podejscie": podejscie})


@login_required(login_url="logowanie")
def punkty(request):
    profil, _ = UserProfile.objects.get_or_create(user=request.user)
    transakcje = PointTransaction.objects.filter(user=request.user).order_by("-created_at")
    return render(request, "quiz/points.html", {"profil": profil, "transakcje": transakcje})


@login_required(login_url="logowanie")
def historia_quizow(request):
    podejscia = QuizAttempt.objects.filter(user=request.user, completed_at__isnull=False).select_related("quiz").order_by("-completed_at")
    return render(request, "quiz/quiz_history.html", {"podejscia": podejscia})



def generuj_kod_nagrody():
    alfabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    while True:
        kod = "QA-" + "".join(secrets.choice(alfabet) for _ in range(4)) + "-" + "".join(secrets.choice(alfabet) for _ in range(4))
        if not RewardRedemption.objects.filter(redemption_code=kod).exists(): return kod


@login_required(login_url="logowanie")
def lista_nagrod(request):
    dzis = timezone.localdate(); profil, _ = UserProfile.objects.get_or_create(user=request.user)
    nagrody = Reward.objects.filter(is_active=True, stock_quantity__gt=0).order_by("cost_points")
    nagrody = [n for n in nagrody if not n.valid_until or n.valid_until >= dzis]
    return render(request, "quiz/reward_list.html", {"profil": profil, "nagrody": nagrody})


@login_required(login_url="logowanie")
@require_POST
def odbierz_nagrode(request, id_nagrody):
    with transaction.atomic():
        nagroda = get_object_or_404(Reward.objects.select_for_update(), id=id_nagrody, is_active=True)
        profil, _ = UserProfile.objects.get_or_create(user=request.user); profil = UserProfile.objects.select_for_update().get(id=profil.id)
        if nagroda.stock_quantity <= 0 or (nagroda.valid_until and nagroda.valid_until < timezone.localdate()):
            messages.error(request, "Nagroda jest niedostępna."); return redirect("lista_nagrod")
        if profil.points < nagroda.cost_points:
            messages.error(request, "Masz za mało punktów."); return redirect("lista_nagrod")
        koszt = nagroda.cost_points; profil.points -= koszt; profil.save(update_fields=["points"]); nagroda.stock_quantity -= 1; nagroda.save(update_fields=["stock_quantity"])
        if nagroda.delivery_method == "EMAIL":
            kod = generuj_kod_nagrody(); status = "EMAIL_PENDING"
        else:
            kod = None; status = "ADDRESS_REQUIRED"
        realizacja = RewardRedemption.objects.create(user=request.user, reward=nagroda, cost_points=koszt, delivery_method=nagroda.delivery_method, redemption_code=kod, status=status)
        PointTransaction.objects.create(user=request.user, points=-koszt, transaction_type="reward", description="Nagroda: " + nagroda.name)
    if realizacja.delivery_method == "EMAIL":
        try:
            wyslane = send_mail("Twoja nagroda w Quiz App", "Kod nagrody: " + realizacja.redemption_code, settings.DEFAULT_FROM_EMAIL, [request.user.email], using="default") == 1
        except Exception:
            wyslane = False
        realizacja.status = "SENT" if wyslane else "EMAIL_FAILED"
        if wyslane: realizacja.email_sent_at = timezone.now()
        realizacja.save(update_fields=["status", "email_sent_at"])
    messages.success(request, "Nagroda została odebrana.")
    return redirect("historia_nagrod")


@login_required(login_url="logowanie")
def historia_nagrod(request):
    realizacje = RewardRedemption.objects.filter(user=request.user).select_related("reward").order_by("-redeemed_at")
    return render(request, "quiz/reward_history.html", {"realizacje_nagrod": realizacje})


@login_required(login_url="logowanie")
def adres_wysylki(request, id_realizacji):
    realizacja = get_object_or_404(RewardRedemption, id=id_realizacji, user=request.user, delivery_method="SHIPPING")
    if request.method == "POST":
        formularz = FormularzAdresuWysylki(request.POST, instance=realizacja)
        if formularz.is_valid():
            realizacja = formularz.save(commit=False); realizacja.status = "READY_TO_SHIP"; realizacja.shipping_address_submitted_at = timezone.now(); realizacja.save(); messages.success(request, "Adres został zapisany."); return redirect("historia_nagrod")
    else: formularz = FormularzAdresuWysylki(instance=realizacja)
    return render(request, "quiz/shipping_address.html", {"formularz": formularz, "realizacja": realizacja})
