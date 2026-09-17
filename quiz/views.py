from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from .forms import FormularzLogowania, FormularzRejestracji
from .models import Answer, PointTransaction, Question, Quiz, QuizAttempt, UserProfile


def strona_glowna(request):
    kontekst = {}
    if request.user.is_authenticated:
        profil, _ = UserProfile.objects.get_or_create(user=request.user)
        kontekst["profil"] = profil
    return render(request, "quiz/home.html", kontekst)


def rejestracja(request):
    if request.user.is_authenticated:
        return redirect("strona_glowna")
    if request.method == "POST":
        formularz = FormularzRejestracji(request.POST)
        if formularz.is_valid():
            uzytkownik = formularz.save()
            UserProfile.objects.create(user=uzytkownik)
            login(request, uzytkownik)
            return redirect("strona_glowna")
    else:
        formularz = FormularzRejestracji()
    return render(request, "quiz/register.html", {"formularz": formularz})


def logowanie(request):
    if request.user.is_authenticated:
        return redirect("strona_glowna")
    if request.method == "POST":
        formularz = FormularzLogowania(request, data=request.POST)
        if formularz.is_valid():
            login(request, formularz.get_user())
            return redirect("strona_glowna")
    else:
        formularz = FormularzLogowania()
    return render(request, "quiz/login.html", {"formularz": formularz})


@require_POST
def wylogowanie(request):
    logout(request)
    return redirect("strona_glowna")


@login_required(login_url="logowanie")
def lista_quizow(request):
    quizy = Quiz.objects.filter(is_active=True).order_by("title")
    return render(request, "quiz/quiz_list.html", {"quizy": quizy})


@login_required(login_url="logowanie")
@require_POST
def rozpocznij_quiz(request, id_quizu):
    quiz = get_object_or_404(Quiz, id=id_quizu, is_active=True)
    pytania = Question.objects.filter(quiz=quiz).order_by("order", "id")
    if not pytania.exists():
        messages.error(request, "Ten quiz nie posiada jeszcze pytań.")
        return redirect("lista_quizow")
    request.session[f"quiz_{quiz.id}_index"] = 0
    request.session[f"quiz_{quiz.id}_score"] = 0
    return redirect("pytanie_quizu", id_quizu=quiz.id)


@login_required(login_url="logowanie")
def pytanie_quizu(request, id_quizu):
    quiz = get_object_or_404(Quiz, id=id_quizu, is_active=True)
    pytania = list(Question.objects.filter(quiz=quiz).order_by("order", "id"))
    indeks = request.session.get(f"quiz_{quiz.id}_index", 0)
    wynik = request.session.get(f"quiz_{quiz.id}_score", 0)

    if indeks >= len(pytania):
        profil, _ = UserProfile.objects.get_or_create(user=request.user)
        stare_punkty = profil.points
        profil.points = max(0, profil.points + wynik)
        zmiana_salda = profil.points - stare_punkty
        profil.save(update_fields=["points"])
        podejscie = QuizAttempt.objects.create(user=request.user, quiz=quiz, score=wynik)
        PointTransaction.objects.create(user=request.user, points=zmiana_salda, transaction_type="quiz", description="Quiz: " + quiz.title)
        request.session.pop(f"quiz_{quiz.id}_index", None)
        request.session.pop(f"quiz_{quiz.id}_score", None)
        return redirect("wynik_quizu", id_quizu=quiz.id, id_podejscia=podejscie.id)

    pytanie = pytania[indeks]
    if request.method == "POST":
        id_odpowiedzi = request.POST.get("odpowiedz")
        odpowiedz = get_object_or_404(Answer, id=id_odpowiedzi, question=pytanie)
        wynik += 10 if odpowiedz.is_correct else -5
        request.session[f"quiz_{quiz.id}_score"] = wynik
        request.session[f"quiz_{quiz.id}_index"] = indeks + 1
        return redirect("pytanie_quizu", id_quizu=quiz.id)

    return render(request, "quiz/quiz_question.html", {"quiz": quiz, "pytanie": pytanie, "numer": indeks + 1, "liczba_pytan": len(pytania)})


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
    podejscia = QuizAttempt.objects.filter(user=request.user).select_related("quiz").order_by("-completed_at")
    return render(request, "quiz/quiz_history.html", {"podejscia": podejscia})
