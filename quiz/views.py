import math
import secrets

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import FormularzLogowania, FormularzRejestracji, FormularzAdresuWysylki
from .models import (
    Answer,
    PointTransaction,
    Quiz,
    QuizAttempt,
    Reward,
    RewardRedemption,
    UserProfile,
)


def _klucz_sesji_podejscia(id_podejscia):
    return "quiz_attempt_" + str(id_podejscia)


def _klucz_aktywnego_podejscia(id_quizu):
    return "active_quiz_attempt_" + str(id_quizu)


def _pozostaly_czas_quizu(podejscie):
    limit = max(1, podejscie.quiz.time_limit_seconds)
    uplynelo_sekund = (timezone.now() - podejscie.started_at).total_seconds()
    return max(0, math.ceil(limit - uplynelo_sekund))


def _pozostaly_czas_pytania(pytanie, podejscie):
    czas_rozpoczecia_pytania = podejscie.current_question_started_at

    if not czas_rozpoczecia_pytania:
        return max(1, pytanie.time_limit_seconds)

    uplynelo_sekund = (timezone.now() - czas_rozpoczecia_pytania).total_seconds()

    return max(
        0,
        math.ceil(max(1, pytanie.time_limit_seconds) - uplynelo_sekund),
    )


def _wyczysc_sesje_podejscia(request, id_quizu, id_podejscia):
    request.session.pop(_klucz_sesji_podejscia(id_podejscia), None)
    request.session.pop(_klucz_aktywnego_podejscia(id_quizu), None)


def _zakoncz_podejscie(id_podejscia, powod_zakonczenia):
    with transaction.atomic():
        podejscie = (
            QuizAttempt.objects
            .select_for_update()
            .select_related("user", "quiz")
            .get(id=id_podejscia)
        )

        if podejscie.completed_at:
            return podejscie

        if powod_zakonczenia == "QUIZ_TIMEOUT":
            liczba_odpowiedzianych = podejscie.correct_answers + podejscie.incorrect_answers
            pozostale_pytania = max(0, podejscie.total_questions - liczba_odpowiedzianych)
            podejscie.incorrect_answers += pozostale_pytania

        wynik_punktowy = (
            podejscie.correct_answers * 10
            + podejscie.incorrect_answers * -5
        )

        podejscie.point_score = wynik_punktowy
        podejscie.balance_change = 0

        if podejscie.is_rewarded_attempt:
            profil, utworzono = UserProfile.objects.get_or_create(
                user=podejscie.user,
            )
            profil = UserProfile.objects.select_for_update().get(
                id=profil.id,
            )

            stare_punkty = profil.points
            nowe_punkty = max(0, stare_punkty + wynik_punktowy)
            zmiana_salda = nowe_punkty - stare_punkty

            profil.points = nowe_punkty
            profil.save(update_fields=["points"])

            podejscie.balance_change = zmiana_salda

            PointTransaction.objects.create(
                user=podejscie.user,
                points=zmiana_salda,
                transaction_type="quiz",
                description=(
                    "Quiz: "
                    + podejscie.quiz.title
                    + " | wynik: "
                    + str(wynik_punktowy)
                    + " pkt"
                ),
            )

        podejscie.finish_reason = powod_zakonczenia
        podejscie.completed_at = timezone.now()
        podejscie.current_question_index = podejscie.total_questions
        podejscie.current_question_started_at = None

        podejscie.save(
            update_fields=[
                "correct_answers",
                "incorrect_answers",
                "point_score",
                "balance_change",
                "finish_reason",
                "completed_at",
                "current_question_index",
                "current_question_started_at",
            ]
        )

        return podejscie


def generuj_kod_nagrody():
    alfabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

    while True:
        czesc1 = "".join(secrets.choice(alfabet) for i in range(4))
        czesc2 = "".join(secrets.choice(alfabet) for i in range(4))
        kod = "QA-" + czesc1 + "-" + czesc2

        if not RewardRedemption.objects.filter(
            redemption_code=kod
        ).exists():
            return kod


def wyslij_email_z_nagroda(uzytkownik, temat, tresc):
    if not uzytkownik.email:
        return False

    try:
        wynik_wysylki = send_mail(
            subject=temat,
            message=tresc,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[uzytkownik.email],
            using="default",
        )
        return wynik_wysylki == 1
    except Exception:
        return False


def strona_glowna(request):
    kontekst = {}

    if request.user.is_authenticated:
        profil, utworzono = UserProfile.objects.get_or_create(
            user=request.user
        )

        podejscia = QuizAttempt.objects.filter(
            user=request.user,
            completed_at__isnull=False,
        )

        realizacje_nagrod = RewardRedemption.objects.filter(
            user=request.user
        )

        ostatnie_podejscia = (
            podejscia
            .select_related("quiz")
            .order_by("-completed_at")[:5]
        )

        kontekst = {
            "profil": profil,
            "liczba_podejsc": podejscia.count(),
            "liczba_odebranych_nagrod": realizacje_nagrod.count(),
            "liczba_dostepnych_quizow": Quiz.objects.filter(
                is_active=True
            ).filter(
                Q(expires_at__isnull=True)
                | Q(expires_at__gt=timezone.now())
            ).count(),
            "ostatnie_podejscia": ostatnie_podejscia,
        }

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

    return render(
        request,
        "quiz/register.html",
        {"formularz": formularz},
    )


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

    return render(
        request,
        "quiz/login.html",
        {"formularz": formularz},
    )


@require_POST
def wylogowanie(request):
    logout(request)
    return redirect("strona_glowna")


@login_required(login_url="logowanie")
def lista_quizow(request):
    teraz = timezone.now()

    quizy = (
        Quiz.objects
        .filter(is_active=True)
        .filter(
            Q(expires_at__isnull=True)
            | Q(expires_at__gt=teraz)
            | Q(
                quizattempt__user=request.user,
                quizattempt__completed_at__isnull=True,
            )
        )
        .distinct()
        .order_by("title")
    )

    elementy_quizow = []

    for quiz in quizy:
        aktywne_podejscie = (
            QuizAttempt.objects
            .filter(
                user=request.user,
                quiz=quiz,
                completed_at__isnull=True,
            )
            .order_by("-started_at")
            .first()
        )

        wygasl = bool(
            quiz.expires_at
            and quiz.expires_at <= teraz
        )

        if aktywne_podejscie:
            elementy_quizow.append(
                {
                    "quiz": quiz,
                    "ma_aktywne_podejscie": True,
                    "bedzie_punktowane": aktywne_podejscie.is_rewarded_attempt,
                    "wygasl": wygasl,
                }
            )
            continue

        juz_punktowane = QuizAttempt.objects.filter(
            user=request.user,
            quiz=quiz,
            is_rewarded_attempt=True,
        ).exists()

        elementy_quizow.append(
            {
                "quiz": quiz,
                "ma_aktywne_podejscie": False,
                "bedzie_punktowane": not juz_punktowane,
                "wygasl": wygasl,
            }
        )

    return render(
        request,
        "quiz/quiz_list.html",
        {"elementy_quizow": elementy_quizow},
    )


@login_required(login_url="logowanie")
@require_POST
def rozpocznij_quiz(request, id_quizu):
    quiz = get_object_or_404(
        Quiz,
        id=id_quizu,
        is_active=True,
    )

    teraz = timezone.now()

                                                                              
    istniejace_podejscie = (
        QuizAttempt.objects
        .filter(
            user=request.user,
            quiz=quiz,
            completed_at__isnull=True,
        )
        .order_by("-started_at")
        .first()
    )

                                                                  
    if (
        not istniejace_podejscie
        and quiz.expires_at
        and quiz.expires_at <= teraz
    ):
        messages.error(
            request,
            "Termin dostępności tego quizu już minął.",
        )
        return redirect("lista_quizow")

    liczba_pytan = quiz.question_set.count()

    if liczba_pytan == 0:
        messages.error(
            request,
            "Ten quiz nie posiada jeszcze pytań.",
        )
        return redirect("lista_quizow")

    with transaction.atomic():
        profil, utworzono = UserProfile.objects.get_or_create(
            user=request.user
        )

        UserProfile.objects.select_for_update().get(id=profil.id)

        aktywne_podejscie = (
            QuizAttempt.objects
            .select_for_update()
            .filter(
                user=request.user,
                quiz=quiz,
                completed_at__isnull=True,
            )
            .order_by("-started_at")
            .first()
        )

        if aktywne_podejscie:
            podejscie = aktywne_podejscie
        else:
            if (
                quiz.expires_at
                and quiz.expires_at <= timezone.now()
            ):
                messages.error(
                    request,
                    "Termin dostępności tego quizu już minął.",
                )
                return redirect("lista_quizow")

            juz_punktowane = QuizAttempt.objects.filter(
                user=request.user,
                quiz=quiz,
                is_rewarded_attempt=True,
            ).exists()

            podejscie = QuizAttempt.objects.create(
                user=request.user,
                quiz=quiz,
                total_questions=liczba_pytan,
                is_rewarded_attempt=not juz_punktowane,
            )

                                                                
                                                   
    if _pozostaly_czas_quizu(podejscie) <= 0:
        podejscie = _zakoncz_podejscie(
            podejscie.id,
            "QUIZ_TIMEOUT",
        )
        _wyczysc_sesje_podejscia(
            request,
            quiz.id,
            podejscie.id,
        )
        return redirect(
            "wynik_quizu",
            id_quizu=quiz.id,
            id_podejscia=podejscie.id,
        )

    request.session[_klucz_aktywnego_podejscia(quiz.id)] = podejscie.id

    klucz_danych = _klucz_sesji_podejscia(podejscie.id)

    if klucz_danych not in request.session:
        request.session[klucz_danych] = {
            "feedback": None,
        }

    return redirect(
        "pytanie_quizu",
        id_quizu=quiz.id,
    )


@login_required(login_url="logowanie")
def pytanie_quizu(request, id_quizu):
    quiz = get_object_or_404(Quiz, id=id_quizu)
    klucz_aktywnego_podejscia = _klucz_aktywnego_podejscia(quiz.id)
    id_podejscia = request.session.get(klucz_aktywnego_podejscia)

                                                                   
                                                       
    if not id_podejscia:
        aktywne_podejscie = (
            QuizAttempt.objects
            .filter(
                user=request.user,
                quiz=quiz,
                completed_at__isnull=True,
            )
            .order_by("-started_at")
            .first()
        )

        if not aktywne_podejscie:
            messages.info(
                request,
                "Rozpocznij quiz z listy quizów.",
            )
            return redirect("lista_quizow")

        id_podejscia = aktywne_podejscie.id
        request.session[klucz_aktywnego_podejscia] = id_podejscia

    podejscie = get_object_or_404(
        QuizAttempt,
        id=id_podejscia,
        user=request.user,
        quiz=quiz,
    )

    if podejscie.completed_at:
        _wyczysc_sesje_podejscia(
            request,
            quiz.id,
            podejscie.id,
        )
        return redirect(
            "wynik_quizu",
            id_quizu=quiz.id,
            id_podejscia=podejscie.id,
        )

    pytania = list(
        quiz.question_set.all().order_by("order", "id")
    )
    pytania = pytania[:podejscie.total_questions]

                                                              
                                                                       
    if _pozostaly_czas_quizu(podejscie) <= 0:
        podejscie = _zakoncz_podejscie(
            podejscie.id,
            "QUIZ_TIMEOUT",
        )
        _wyczysc_sesje_podejscia(
            request,
            quiz.id,
            podejscie.id,
        )
        return redirect(
            "wynik_quizu",
            id_quizu=quiz.id,
            id_podejscia=podejscie.id,
        )

    klucz_danych = _klucz_sesji_podejscia(podejscie.id)
    dane_quizu = request.session.get(klucz_danych)

    if not dane_quizu:
        dane_quizu = {
            "feedback": None,
        }
        request.session[klucz_danych] = dane_quizu

    informacja_zwrotna = dane_quizu.get("feedback")

                                                                                
    if informacja_zwrotna:
        if request.method == "POST":
            akcja = request.POST.get("action")

            if akcja == "next":
                dane_quizu["feedback"] = None
                request.session[klucz_danych] = dane_quizu

                liczba_odpowiedzianych = (
                    podejscie.correct_answers
                    + podejscie.incorrect_answers
                )

                if liczba_odpowiedzianych >= len(pytania):
                    podejscie = _zakoncz_podejscie(
                        podejscie.id,
                        "COMPLETED",
                    )
                    _wyczysc_sesje_podejscia(
                        request,
                        quiz.id,
                        podejscie.id,
                    )
                    return redirect(
                        "wynik_quizu",
                        id_quizu=quiz.id,
                        id_podejscia=podejscie.id,
                    )

                return redirect(
                    "pytanie_quizu",
                    id_quizu=quiz.id,
                )

            if akcja == "quiz_timeout":
                return redirect(
                    "pytanie_quizu",
                    id_quizu=quiz.id,
                )

        return render(
            request,
            "quiz/quiz_question.html",
            {
                "quiz": quiz,
                "podejscie": podejscie,
                "informacja_zwrotna": informacja_zwrotna,
                "numer_pytania": informacja_zwrotna["question_number"],
                "liczba_pytan": podejscie.total_questions,
                "pozostaly_czas_quizu": _pozostaly_czas_quizu(
                    podejscie
                ),
            },
        )

                                                                         
                                                                    
    indeks_pytania = (
        podejscie.correct_answers
        + podejscie.incorrect_answers
    )

    if indeks_pytania >= len(pytania):
        podejscie = _zakoncz_podejscie(
            podejscie.id,
            "COMPLETED",
        )
        _wyczysc_sesje_podejscia(
            request,
            quiz.id,
            podejscie.id,
        )
        return redirect(
            "wynik_quizu",
            id_quizu=quiz.id,
            id_podejscia=podejscie.id,
        )

    pytanie = pytania[indeks_pytania]

                                                       
                                                                           
    if (
        podejscie.current_question_index != indeks_pytania
        or podejscie.current_question_started_at is None
    ):
        with transaction.atomic():
            zablokowane_podejscie = (
                QuizAttempt.objects
                .select_for_update()
                .get(id=podejscie.id)
            )

            indeks_zablokowanego_podejscia = (
                zablokowane_podejscie.correct_answers
                + zablokowane_podejscie.incorrect_answers
            )

            if indeks_zablokowanego_podejscia != indeks_pytania:
                return redirect(
                    "pytanie_quizu",
                    id_quizu=quiz.id,
                )

            if (
                zablokowane_podejscie.current_question_index != indeks_pytania
                or zablokowane_podejscie.current_question_started_at is None
            ):
                zablokowane_podejscie.current_question_index = indeks_pytania
                zablokowane_podejscie.current_question_started_at = timezone.now()
                zablokowane_podejscie.save(
                    update_fields=[
                        "current_question_index",
                        "current_question_started_at",
                    ]
                )

            podejscie = zablokowane_podejscie

    blad = None

    if request.method == "POST":
        akcja = request.POST.get("action")

        if akcja == "quiz_timeout":
            return redirect(
                "pytanie_quizu",
                id_quizu=quiz.id,
            )

        przeslany_indeks = request.POST.get("question_index")

        if (
            przeslany_indeks is None
            or przeslany_indeks != str(indeks_pytania)
        ):
            return redirect(
                "pytanie_quizu",
                id_quizu=quiz.id,
            )

        odpowiedz = None
        id_odpowiedzi = request.POST.get("answer")
        przekroczenie_czasu_klienta = request.POST.get("timeout") == "1"

        if id_odpowiedzi:
            odpowiedz = get_object_or_404(
                Answer,
                id=id_odpowiedzi,
                question=pytanie,
            )

        with transaction.atomic():
            zablokowane_podejscie = (
                QuizAttempt.objects
                .select_for_update()
                .get(id=podejscie.id)
            )

            if zablokowane_podejscie.completed_at:
                return redirect(
                    "wynik_quizu",
                    id_quizu=quiz.id,
                    id_podejscia=zablokowane_podejscie.id,
                )

            liczba_odpowiedzianych = (
                zablokowane_podejscie.correct_answers
                + zablokowane_podejscie.incorrect_answers
            )

            if liczba_odpowiedzianych != indeks_pytania:
                return redirect(
                    "pytanie_quizu",
                    id_quizu=quiz.id,
                )

            czas_rozpoczecia_pytania = zablokowane_podejscie.current_question_started_at

            if czas_rozpoczecia_pytania is None:
                return redirect(
                    "pytanie_quizu",
                    id_quizu=quiz.id,
                )

            uplynelo_sekund = (timezone.now() - czas_rozpoczecia_pytania).total_seconds()
            przekroczenie_czasu_serwera = (
                uplynelo_sekund >= max(1, pytanie.time_limit_seconds)
            )
            przekroczenie_czasu_pytania = przekroczenie_czasu_serwera or przekroczenie_czasu_klienta

            if not przekroczenie_czasu_pytania and odpowiedz is None:
                blad = "Wybierz odpowiedź przed przejściem dalej."
            else:
                czy_poprawna = bool(
                    odpowiedz is not None
                    and odpowiedz.is_correct
                    and not przekroczenie_czasu_pytania
                )

                if czy_poprawna:
                    zablokowane_podejscie.correct_answers += 1
                else:
                    zablokowane_podejscie.incorrect_answers += 1

                zablokowane_podejscie.current_question_index = indeks_pytania + 1
                zablokowane_podejscie.current_question_started_at = None

                zablokowane_podejscie.save(
                    update_fields=[
                        "correct_answers",
                        "incorrect_answers",
                        "current_question_index",
                        "current_question_started_at",
                    ]
                )

                podejscie = zablokowane_podejscie

                poprawna_odpowiedz = (
                    pytanie.answer_set
                    .filter(is_correct=True)
                    .first()
                )

                if not podejscie.is_rewarded_attempt:
                    dane_quizu["feedback"] = {
                        "question_number": indeks_pytania + 1,
                        "question_text": pytanie.text,
                        "is_correct": czy_poprawna,
                        "timed_out": przekroczenie_czasu_pytania,
                        "selected_answer": (
                            odpowiedz.text if odpowiedz else ""
                        ),
                        "correct_answer": (
                            poprawna_odpowiedz.text
                            if poprawna_odpowiedz
                            else ""
                        ),
                    }

                request.session[klucz_danych] = dane_quizu

                nastepny_indeks = indeks_pytania + 1

                if (
                    podejscie.is_rewarded_attempt
                    and nastepny_indeks >= len(pytania)
                ):
                    podejscie = _zakoncz_podejscie(
                        podejscie.id,
                        "COMPLETED",
                    )
                    _wyczysc_sesje_podejscia(
                        request,
                        quiz.id,
                        podejscie.id,
                    )
                    return redirect(
                        "wynik_quizu",
                        id_quizu=quiz.id,
                        id_podejscia=podejscie.id,
                    )

                return redirect(
                    "pytanie_quizu",
                    id_quizu=quiz.id,
                )

    return render(
        request,
        "quiz/quiz_question.html",
        {
            "quiz": quiz,
            "podejscie": podejscie,
            "pytanie": pytanie,
            "numer_pytania": indeks_pytania + 1,
            "liczba_pytan": podejscie.total_questions,
            "pozostaly_czas_pytania": _pozostaly_czas_pytania(
                pytanie,
                podejscie,
            ),
            "pozostaly_czas_quizu": _pozostaly_czas_quizu(
                podejscie
            ),
            "informacja_zwrotna": None,
            "blad": blad,
        },
    )


@login_required(login_url="logowanie")
def wynik_quizu(request, id_quizu, id_podejscia):
    podejscie = get_object_or_404(
        QuizAttempt.objects.select_related("quiz"),
        id=id_podejscia,
        quiz_id=id_quizu,
        user=request.user,
        completed_at__isnull=False,
    )

    profil, utworzono = UserProfile.objects.get_or_create(
        user=request.user
    )

    return render(
        request,
        "quiz/quiz_result.html",
        {
            "podejscie": podejscie,
            "quiz": podejscie.quiz,
            "profil": profil,
        },
    )


@login_required(login_url="logowanie")
def punkty(request):
    profil, utworzono = UserProfile.objects.get_or_create(
        user=request.user
    )

    transakcje = (
        PointTransaction.objects
        .filter(user=request.user)
        .order_by("-created_at")
    )

    return render(
        request,
        "quiz/points.html",
        {
            "profil": profil,
            "transakcje": transakcje,
        },
    )


@login_required(login_url="logowanie")
def historia_quizow(request):
    podejscia = (
        QuizAttempt.objects
        .filter(
            user=request.user,
            completed_at__isnull=False,
        )
        .select_related("quiz")
        .order_by("-completed_at")
    )

    return render(
        request,
        "quiz/quiz_history.html",
        {"podejscia": podejscia},
    )


@login_required(login_url="logowanie")
def lista_nagrod(request):
    dzisiaj = timezone.localdate()

    Reward.objects.filter(
        is_active=True,
        valid_until__isnull=False,
        valid_until__lt=dzisiaj,
    ).update(is_active=False)

    nagrody = (
        Reward.objects
        .filter(
            is_active=True,
            stock_quantity__gt=0,
        )
        .filter(
            Q(valid_until__isnull=True)
            | Q(valid_until__gte=dzisiaj)
        )
        .order_by("cost_points")
    )

    profil, utworzono = UserProfile.objects.get_or_create(
        user=request.user
    )

    return render(
        request,
        "quiz/reward_list.html",
        {
            "nagrody": nagrody,
            "profil": profil,
        },
    )


@login_required(login_url="logowanie")
@require_POST
def odbierz_nagrode(request, id_nagrody):
    with transaction.atomic():
        nagroda = get_object_or_404(
            Reward.objects.select_for_update(),
            id=id_nagrody,
        )

        profil, utworzono = UserProfile.objects.get_or_create(
            user=request.user
        )
        profil = UserProfile.objects.select_for_update().get(
            id=profil.id
        )

        dzisiaj = timezone.localdate()

        if nagroda.valid_until and nagroda.valid_until < dzisiaj:
            nagroda.is_active = False
            nagroda.save(update_fields=["is_active"])
            messages.error(
                request,
                "Termin ważności tej nagrody minął.",
            )
            return redirect("lista_nagrod")

        if not nagroda.is_active:
            messages.error(
                request,
                "Ta nagroda nie jest już dostępna.",
            )
            return redirect("lista_nagrod")

        if nagroda.stock_quantity <= 0:
            nagroda.is_active = False
            nagroda.save(update_fields=["is_active"])
            messages.error(
                request,
                "Ta nagroda nie jest już dostępna.",
            )
            return redirect("lista_nagrod")

        if profil.points < nagroda.cost_points:
            messages.error(
                request,
                "Nie masz wystarczającej liczby punktów.",
            )
            return redirect("lista_nagrod")

        koszt = nagroda.cost_points

        profil.points -= koszt
        nagroda.stock_quantity -= 1

        if nagroda.stock_quantity == 0:
            nagroda.is_active = False

        profil.save(update_fields=["points"])
        nagroda.save(
            update_fields=[
                "stock_quantity",
                "is_active",
            ]
        )

        if nagroda.delivery_method == "EMAIL":
            realizacja = RewardRedemption.objects.create(
                user=request.user,
                reward=nagroda,
                cost_points=koszt,
                delivery_method="EMAIL",
                redemption_code=generuj_kod_nagrody(),
                status="EMAIL_PENDING",
            )
        else:
            realizacja = RewardRedemption.objects.create(
                user=request.user,
                reward=nagroda,
                cost_points=koszt,
                delivery_method="SHIPPING",
                status="ADDRESS_REQUIRED",
                shipping_country="Polska",
            )

        PointTransaction.objects.create(
            user=request.user,
            points=-koszt,
            transaction_type="reward",
            description="Nagroda: " + nagroda.name,
        )

    if realizacja.delivery_method == "EMAIL":
        wiadomosc = (
            "Cześć "
            + request.user.username
            + ",\n\nodebrałeś nagrodę: "
            + nagroda.name
            + ".\n\nTwój kod nagrody:\n"
            + realizacja.redemption_code
            + "\n\nKoszt nagrody: "
            + str(koszt)
            + " pkt.\n\nKod znajdziesz również "
            + 'w zakładce "Moje nagrody" w aplikacji Quiz App.'
        )

        wyslano = wyslij_email_z_nagroda(
            request.user,
            "Quiz App - Twoja nagroda: " + nagroda.name,
            wiadomosc,
        )

        if wyslano:
            realizacja.status = "SENT"
            realizacja.email_sent_at = timezone.now()
            realizacja.save(
                update_fields=[
                    "status",
                    "email_sent_at",
                ]
            )
            messages.success(
                request,
                "Nagroda została wysłana na Twój adres e-mail.",
            )
        else:
            realizacja.status = "EMAIL_FAILED"
            realizacja.save(update_fields=["status"])
            messages.warning(
                request,
                "Nagroda została zapisana na Twoim koncie, "
                "ale nie udało się wysłać wiadomości e-mail. "
                'Kod jest dostępny w zakładce "Moje nagrody".',
            )

        return redirect("historia_nagrod")

    wiadomosc = (
        "Cześć "
        + request.user.username
        + ",\n\nodebrałeś nagrodę fizyczną: "
        + nagroda.name
        + ".\n\nNagroda została dla Ciebie zarezerwowana.\n"
        + "Abyśmy mogli ją wysłać, uzupełnij adres dostawy "
        + 'w zakładce "Moje nagrody".'
    )

    wyslij_email_z_nagroda(
        request.user,
        "Quiz App - uzupełnij adres do wysyłki nagrody",
        wiadomosc,
    )

    messages.success(
        request,
        "Nagroda została zarezerwowana. "
        "Uzupełnij teraz adres do wysyłki.",
    )

    return redirect(
        "adres_wysylki",
        id_realizacji=realizacja.id,
    )


@login_required(login_url="logowanie")
def historia_nagrod(request):
    realizacje_nagrod = (
        RewardRedemption.objects
        .filter(user=request.user)
        .select_related("reward")
        .order_by("-redeemed_at")
    )

    return render(
        request,
        "quiz/reward_history.html",
        {"realizacje_nagrod": realizacje_nagrod},
    )


@login_required(login_url="logowanie")
def adres_wysylki(request, id_realizacji):
    realizacja = get_object_or_404(
        RewardRedemption.objects.select_related("reward"),
        id=id_realizacji,
        user=request.user,
        delivery_method="SHIPPING",
    )

    if realizacja.status == "SHIPPED":
        messages.info(
            request,
            "Ta nagroda została już wysłana.",
        )
        return redirect("historia_nagrod")

    if request.method == "POST":
        formularz = FormularzAdresuWysylki(
            request.POST,
            instance=realizacja,
        )

        if formularz.is_valid():
            with transaction.atomic():
                zapisany_formularz = formularz.save(commit=False)
                zapisany_formularz.status = "READY_TO_SHIP"
                zapisany_formularz.shipping_address_submitted_at = timezone.now()
                zapisany_formularz.save()

            wiadomosc = (
                "Cześć "
                + request.user.username
                + ',\n\ndane do wysyłki nagrody "'
                + realizacja.reward.name
                + '" zostały zapisane.\n\n'
                + "Nagroda oczekuje teraz na przygotowanie do wysyłki."
            )

            wyslij_email_z_nagroda(
                request.user,
                "Quiz App - zapisano dane do wysyłki",
                wiadomosc,
            )

            messages.success(
                request,
                "Adres został zapisany. "
                "Nagroda oczekuje na wysyłkę.",
            )
            return redirect("historia_nagrod")
    else:
        formularz = FormularzAdresuWysylki(instance=realizacja)

    return render(
        request,
        "quiz/shipping_address.html",
        {
            "formularz": formularz,
            "realizacja": realizacja,
        },
    )
