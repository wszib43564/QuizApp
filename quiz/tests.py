from datetime import timedelta
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.forms.models import inlineformset_factory
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from .admin import AdministracjaProfiliUzytkownikow, ZestawFormularzyOdpowiedzi
from .models import (
    Answer,
    PointTransaction,
    Question,
    Quiz,
    QuizAttempt,
    Reward,
    RewardRedemption,
    UserProfile,
)
from .views import _zakoncz_podejscie, generuj_kod_nagrody


class BazaTestow(TestCase):
    haslo = "TestoweHaslo123!"

    def utworz_uzytkownika(self, nazwa="testowy", email="test@example.com", punkty=0):
        uzytkownik = User.objects.create_user(
            username=nazwa,
            email=email,
            password=self.haslo,
        )
        profil = UserProfile.objects.create(user=uzytkownik, points=punkty)
        return uzytkownik, profil

    def utworz_quiz(self, liczba_pytan=3, limit_quizu=120, limit_pytania=20, expires_at=None):
        quiz = Quiz.objects.create(
            title="Quiz testowy",
            description="Quiz używany przez testy automatyczne.",
            is_active=True,
            time_limit_seconds=limit_quizu,
            expires_at=expires_at,
        )

        pytania = []
        for numer in range(1, liczba_pytan + 1):
            pytanie = Question.objects.create(
                quiz=quiz,
                text=f"Pytanie {numer}",
                order=numer,
                time_limit_seconds=limit_pytania,
            )
            poprawna = Answer.objects.create(
                question=pytanie,
                text=f"Poprawna {numer}",
                is_correct=True,
            )
            bledna = Answer.objects.create(
                question=pytanie,
                text=f"Błędna {numer}",
                is_correct=False,
            )
            pytania.append((pytanie, poprawna, bledna))

        return quiz, pytania

    def rozpocznij(self, uzytkownik, quiz):
        self.client.force_login(uzytkownik)
        odpowiedz = self.client.post(reverse("rozpocznij_quiz", args=[quiz.id]))
        self.assertEqual(odpowiedz.status_code, 302)
        return QuizAttempt.objects.filter(user=uzytkownik, quiz=quiz).latest("id")

    def otworz_biezace_pytanie(self, quiz):
        return self.client.get(reverse("pytanie_quizu", args=[quiz.id]))


class TestyUzytkownikowIBiezpiecznegoDostepu(BazaTestow):
    def test_rejestracja_tworzy_konto_i_profil(self):
        odpowiedz = self.client.post(
            reverse("rejestracja"),
            {
                "username": "nowy_uzytkownik",
                "email": "nowy@example.com",
                "password1": self.haslo,
                "password2": self.haslo,
            },
        )

        self.assertEqual(odpowiedz.status_code, 302)
        uzytkownik = User.objects.get(username="nowy_uzytkownik")
        self.assertTrue(UserProfile.objects.filter(user=uzytkownik).exists())
        self.assertTrue(odpowiedz.wsgi_request.user.is_authenticated)

    def test_rejestracja_odrzuca_rozne_hasla(self):
        odpowiedz = self.client.post(
            reverse("rejestracja"),
            {
                "username": "bledny_uzytkownik",
                "email": "bledny@example.com",
                "password1": self.haslo,
                "password2": "InneHaslo123!",
            },
        )

        self.assertEqual(odpowiedz.status_code, 200)
        self.assertFalse(User.objects.filter(username="bledny_uzytkownik").exists())

    def test_haslo_nie_jest_zapisane_jawnym_tekstem(self):
        uzytkownik, profil = self.utworz_uzytkownika()

        self.assertNotEqual(uzytkownik.password, self.haslo)
        self.assertTrue(uzytkownik.check_password(self.haslo))

    def test_logowanie_poprawnymi_danymi(self):
        self.utworz_uzytkownika()

        odpowiedz = self.client.post(
            reverse("logowanie"),
            {"username": "testowy", "password": self.haslo},
        )

        self.assertEqual(odpowiedz.status_code, 302)
        self.assertEqual(int(self.client.session["_auth_user_id"]), User.objects.get(username="testowy").id)

    def test_logowanie_blednym_haslem_jest_odrzucone(self):
        self.utworz_uzytkownika()

        odpowiedz = self.client.post(
            reverse("logowanie"),
            {"username": "testowy", "password": "BledneHaslo123!"},
        )

        self.assertEqual(odpowiedz.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_wylogowanie_konczy_sesje(self):
        uzytkownik, profil = self.utworz_uzytkownika()
        self.client.force_login(uzytkownik)

        odpowiedz = self.client.post(reverse("wylogowanie"))

        self.assertEqual(odpowiedz.status_code, 302)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_chronione_widoki_wymagaja_logowania(self):
        nazwy = ["lista_quizow", "punkty", "historia_quizow", "lista_nagrod", "historia_nagrod"]

        for nazwa in nazwy:
            with self.subTest(widok=nazwa):
                odpowiedz = self.client.get(reverse(nazwa))
                self.assertEqual(odpowiedz.status_code, 302)
                self.assertIn(reverse("logowanie"), odpowiedz.url)

    def test_zwykly_uzytkownik_nie_ma_dostepu_do_panelu_admina(self):
        uzytkownik, profil = self.utworz_uzytkownika()
        self.client.force_login(uzytkownik)

        odpowiedz = self.client.get("/admin/")

        self.assertEqual(odpowiedz.status_code, 302)
        self.assertIn("/admin/login/", odpowiedz.url)

    def test_administrator_ma_dostep_do_panelu_admina(self):
        administrator = User.objects.create_superuser(
            username="administrator",
            email="admin@example.com",
            password=self.haslo,
        )
        self.client.force_login(administrator)

        odpowiedz = self.client.get("/admin/")

        self.assertEqual(odpowiedz.status_code, 200)

    def test_csrf_blokuje_post_bez_tokenu(self):
        uzytkownik, profil = self.utworz_uzytkownika(punkty=100)
        nagroda = Reward.objects.create(
            name="Nagroda CSRF",
            cost_points=20,
            stock_quantity=2,
            delivery_method="EMAIL",
            is_active=True,
        )
        klient_csrf = Client(enforce_csrf_checks=True)
        klient_csrf.force_login(uzytkownik)

        odpowiedz = klient_csrf.post(reverse("odbierz_nagrode", args=[nagroda.id]))

        self.assertEqual(odpowiedz.status_code, 403)
        profil.refresh_from_db()
        self.assertEqual(profil.points, 100)


class TestyQuizowIPunktow(BazaTestow):
    def test_lista_quizow_pokazuje_status_pierwszej_proby(self):
        uzytkownik, profil = self.utworz_uzytkownika()
        quiz, pytania = self.utworz_quiz()
        self.client.force_login(uzytkownik)

        odpowiedz = self.client.get(reverse("lista_quizow"))

        self.assertEqual(odpowiedz.status_code, 200)
        element = odpowiedz.context["elementy_quizow"][0]
        self.assertTrue(element["bedzie_punktowane"])
        self.assertFalse(element["ma_aktywne_podejscie"])

    def test_pierwsze_podejscie_jest_punktowane(self):
        uzytkownik, profil = self.utworz_uzytkownika()
        quiz, pytania = self.utworz_quiz()

        podejscie = self.rozpocznij(uzytkownik, quiz)

        self.assertTrue(podejscie.is_rewarded_attempt)
        self.assertEqual(podejscie.total_questions, 3)

    def test_kolejne_podejscie_nie_jest_punktowane(self):
        uzytkownik, profil = self.utworz_uzytkownika()
        quiz, pytania = self.utworz_quiz()
        QuizAttempt.objects.create(
            user=uzytkownik,
            quiz=quiz,
            total_questions=3,
            is_rewarded_attempt=True,
            completed_at=timezone.now(),
            finish_reason="COMPLETED",
        )

        podejscie = self.rozpocznij(uzytkownik, quiz)

        self.assertFalse(podejscie.is_rewarded_attempt)

    def test_poprawna_odpowiedz_daje_10_punktow(self):
        uzytkownik, profil = self.utworz_uzytkownika()
        quiz, pytania = self.utworz_quiz(liczba_pytan=1)
        podejscie = self.rozpocznij(uzytkownik, quiz)
        self.otworz_biezace_pytanie(quiz)

        odpowiedz = self.client.post(
            reverse("pytanie_quizu", args=[quiz.id]),
            {"question_index": "0", "answer": str(pytania[0][1].id)},
        )

        self.assertEqual(odpowiedz.status_code, 302)
        podejscie.refresh_from_db()
        profil.refresh_from_db()
        self.assertEqual(podejscie.correct_answers, 1)
        self.assertEqual(podejscie.incorrect_answers, 0)
        self.assertEqual(podejscie.point_score, 10)
        self.assertEqual(podejscie.balance_change, 10)
        self.assertEqual(profil.points, 10)
        self.assertTrue(PointTransaction.objects.filter(user=uzytkownik, points=10, transaction_type="quiz").exists())

    def test_bledna_odpowiedz_odejmuje_5_punktow(self):
        uzytkownik, profil = self.utworz_uzytkownika(punkty=20)
        quiz, pytania = self.utworz_quiz(liczba_pytan=1)
        podejscie = self.rozpocznij(uzytkownik, quiz)
        self.otworz_biezace_pytanie(quiz)

        self.client.post(
            reverse("pytanie_quizu", args=[quiz.id]),
            {"question_index": "0", "answer": str(pytania[0][2].id)},
        )

        podejscie.refresh_from_db()
        profil.refresh_from_db()
        self.assertEqual(podejscie.point_score, -5)
        self.assertEqual(podejscie.balance_change, -5)
        self.assertEqual(profil.points, 15)

    def test_saldo_nie_spada_ponizej_zera(self):
        uzytkownik, profil = self.utworz_uzytkownika(punkty=10)
        quiz, pytania = self.utworz_quiz(liczba_pytan=3)
        podejscie = QuizAttempt.objects.create(
            user=uzytkownik,
            quiz=quiz,
            total_questions=3,
            correct_answers=0,
            incorrect_answers=3,
            is_rewarded_attempt=True,
        )

        _zakoncz_podejscie(podejscie.id, "COMPLETED")

        podejscie.refresh_from_db()
        profil.refresh_from_db()
        self.assertEqual(podejscie.point_score, -15)
        self.assertEqual(podejscie.balance_change, -10)
        self.assertEqual(profil.points, 0)

    def test_drugie_podejscie_zapisuje_wynik_bez_zmiany_salda(self):
        uzytkownik, profil = self.utworz_uzytkownika(punkty=50)
        quiz, pytania = self.utworz_quiz(liczba_pytan=1)
        QuizAttempt.objects.create(
            user=uzytkownik,
            quiz=quiz,
            total_questions=1,
            correct_answers=1,
            point_score=10,
            balance_change=10,
            is_rewarded_attempt=True,
            completed_at=timezone.now(),
            finish_reason="COMPLETED",
        )
        podejscie = self.rozpocznij(uzytkownik, quiz)
        self.otworz_biezace_pytanie(quiz)

        self.client.post(
            reverse("pytanie_quizu", args=[quiz.id]),
            {"question_index": "0", "answer": str(pytania[0][1].id)},
        )
        self.client.post(reverse("pytanie_quizu", args=[quiz.id]), {"action": "next"})

        podejscie.refresh_from_db()
        profil.refresh_from_db()
        self.assertFalse(podejscie.is_rewarded_attempt)
        self.assertEqual(podejscie.point_score, 10)
        self.assertEqual(podejscie.balance_change, 0)
        self.assertEqual(profil.points, 50)

    def test_pierwsza_proba_nie_pokazuje_feedbacku_po_pytaniu(self):
        uzytkownik, profil = self.utworz_uzytkownika()
        quiz, pytania = self.utworz_quiz(liczba_pytan=2)
        podejscie = self.rozpocznij(uzytkownik, quiz)
        self.otworz_biezace_pytanie(quiz)

        self.client.post(
            reverse("pytanie_quizu", args=[quiz.id]),
            {"question_index": "0", "answer": str(pytania[0][1].id)},
        )

        dane = self.client.session.get("quiz_attempt_" + str(podejscie.id))
        self.assertIsNone(dane.get("feedback"))

    def test_kolejna_proba_pokazuje_feedback_i_poprawna_odpowiedz(self):
        uzytkownik, profil = self.utworz_uzytkownika()
        quiz, pytania = self.utworz_quiz(liczba_pytan=2)
        QuizAttempt.objects.create(
            user=uzytkownik,
            quiz=quiz,
            total_questions=2,
            is_rewarded_attempt=True,
            completed_at=timezone.now(),
            finish_reason="COMPLETED",
        )
        podejscie = self.rozpocznij(uzytkownik, quiz)
        self.otworz_biezace_pytanie(quiz)

        self.client.post(
            reverse("pytanie_quizu", args=[quiz.id]),
            {"question_index": "0", "answer": str(pytania[0][2].id)},
        )

        dane = self.client.session.get("quiz_attempt_" + str(podejscie.id))
        self.assertIsNotNone(dane["feedback"])
        self.assertFalse(dane["feedback"]["is_correct"])
        self.assertEqual(dane["feedback"]["correct_answer"], pytania[0][1].text)

    def test_serwer_weryfikuje_przekroczenie_czasu_pytania(self):
        uzytkownik, profil = self.utworz_uzytkownika(punkty=20)
        quiz, pytania = self.utworz_quiz(liczba_pytan=1, limit_pytania=2)
        podejscie = self.rozpocznij(uzytkownik, quiz)
        self.otworz_biezace_pytanie(quiz)
        podejscie.refresh_from_db()
        podejscie.current_question_started_at = timezone.now() - timedelta(seconds=5)
        podejscie.save(update_fields=["current_question_started_at"])

        self.client.post(
            reverse("pytanie_quizu", args=[quiz.id]),
            {"question_index": "0", "answer": str(pytania[0][1].id)},
        )

        podejscie.refresh_from_db()
        self.assertEqual(podejscie.correct_answers, 0)
        self.assertEqual(podejscie.incorrect_answers, 1)
        self.assertEqual(podejscie.point_score, -5)

    def test_timeout_calego_quizu_uznaje_pozostale_pytania_za_bledne(self):
        uzytkownik, profil = self.utworz_uzytkownika(punkty=20)
        quiz, pytania = self.utworz_quiz(liczba_pytan=3, limit_quizu=2)
        podejscie = self.rozpocznij(uzytkownik, quiz)
        podejscie.started_at = timezone.now() - timedelta(seconds=5)
        podejscie.save(update_fields=["started_at"])

        odpowiedz = self.client.get(reverse("pytanie_quizu", args=[quiz.id]))

        self.assertEqual(odpowiedz.status_code, 302)
        podejscie.refresh_from_db()
        profil.refresh_from_db()
        self.assertEqual(podejscie.finish_reason, "QUIZ_TIMEOUT")
        self.assertEqual(podejscie.incorrect_answers, 3)
        self.assertEqual(podejscie.point_score, -15)
        self.assertEqual(profil.points, 5)

    def test_odswiezenie_strony_nie_resetuje_czasu_pytania(self):
        uzytkownik, profil = self.utworz_uzytkownika()
        quiz, pytania = self.utworz_quiz(liczba_pytan=1)
        podejscie = self.rozpocznij(uzytkownik, quiz)
        self.otworz_biezace_pytanie(quiz)
        podejscie.refresh_from_db()
        pierwszy_czas = podejscie.current_question_started_at

        self.client.get(reverse("pytanie_quizu", args=[quiz.id]))

        podejscie.refresh_from_db()
        self.assertEqual(podejscie.current_question_started_at, pierwszy_czas)

    def test_powrot_po_utracie_kluczy_sesji_kontynuuje_podejscie(self):
        uzytkownik, profil = self.utworz_uzytkownika()
        quiz, pytania = self.utworz_quiz(liczba_pytan=1)
        podejscie = self.rozpocznij(uzytkownik, quiz)
        self.otworz_biezace_pytanie(quiz)
        podejscie.refresh_from_db()
        pierwszy_czas = podejscie.current_question_started_at

        sesja = self.client.session
        sesja.pop("active_quiz_attempt_" + str(quiz.id), None)
        sesja.pop("quiz_attempt_" + str(podejscie.id), None)
        sesja.save()

        odpowiedz = self.client.get(reverse("pytanie_quizu", args=[quiz.id]))

        self.assertEqual(odpowiedz.status_code, 200)
        podejscie.refresh_from_db()
        self.assertEqual(podejscie.current_question_started_at, pierwszy_czas)
        self.assertEqual(self.client.session["active_quiz_attempt_" + str(quiz.id)], podejscie.id)

    def test_wygasly_quiz_blokuje_nowe_podejscie(self):
        uzytkownik, profil = self.utworz_uzytkownika()
        quiz, pytania = self.utworz_quiz(expires_at=timezone.now() - timedelta(minutes=1))
        self.client.force_login(uzytkownik)

        odpowiedz = self.client.post(reverse("rozpocznij_quiz", args=[quiz.id]))

        self.assertEqual(odpowiedz.status_code, 302)
        self.assertEqual(QuizAttempt.objects.filter(user=uzytkownik, quiz=quiz).count(), 0)

    def test_rozpoczety_quiz_mozna_kontynuowac_po_wygasnieciu(self):
        uzytkownik, profil = self.utworz_uzytkownika()
        quiz, pytania = self.utworz_quiz(expires_at=timezone.now() + timedelta(minutes=5))
        podejscie = self.rozpocznij(uzytkownik, quiz)
        quiz.expires_at = timezone.now() - timedelta(minutes=1)
        quiz.save(update_fields=["expires_at"])

        odpowiedz = self.client.post(reverse("rozpocznij_quiz", args=[quiz.id]))

        self.assertEqual(odpowiedz.status_code, 302)
        self.assertEqual(QuizAttempt.objects.filter(user=uzytkownik, quiz=quiz).count(), 1)
        podejscie.refresh_from_db()
        self.assertIsNone(podejscie.completed_at)

    def test_historia_quizow_pokazuje_tylko_zakonczone_podejscia_uzytkownika(self):
        uzytkownik, profil = self.utworz_uzytkownika()
        inny, inny_profil = self.utworz_uzytkownika("inny", "inny@example.com")
        quiz, pytania = self.utworz_quiz()
        zakonczone = QuizAttempt.objects.create(
            user=uzytkownik,
            quiz=quiz,
            total_questions=3,
            completed_at=timezone.now(),
            finish_reason="COMPLETED",
        )
        QuizAttempt.objects.create(user=uzytkownik, quiz=quiz, total_questions=3)
        QuizAttempt.objects.create(
            user=inny,
            quiz=quiz,
            total_questions=3,
            completed_at=timezone.now(),
            finish_reason="COMPLETED",
        )
        self.client.force_login(uzytkownik)

        odpowiedz = self.client.get(reverse("historia_quizow"))

        self.assertEqual(list(odpowiedz.context["podejscia"]), [zakonczone])

    def test_zakonczenie_punktowanej_proby_jest_atomowe(self):
        uzytkownik, profil = self.utworz_uzytkownika(punkty=10)
        quiz, pytania = self.utworz_quiz(liczba_pytan=1)
        podejscie = QuizAttempt.objects.create(
            user=uzytkownik,
            quiz=quiz,
            total_questions=1,
            correct_answers=1,
            is_rewarded_attempt=True,
        )

        with patch("quiz.views.PointTransaction.objects.create", side_effect=RuntimeError("test rollback")):
            with self.assertRaises(RuntimeError):
                _zakoncz_podejscie(podejscie.id, "COMPLETED")

        profil.refresh_from_db()
        podejscie.refresh_from_db()
        self.assertEqual(profil.points, 10)
        self.assertIsNone(podejscie.completed_at)
        self.assertEqual(PointTransaction.objects.count(), 0)


class TestyNagrod(BazaTestow):
    def test_lista_nagrod_pokazuje_tylko_dostepne_i_dezaktywuje_wygasle(self):
        uzytkownik, profil = self.utworz_uzytkownika(punkty=100)
        dostepna = Reward.objects.create(name="Dostępna", cost_points=10, stock_quantity=2, is_active=True)
        bez_stanu = Reward.objects.create(name="Brak stanu", cost_points=10, stock_quantity=0, is_active=True)
        wygasla = Reward.objects.create(
            name="Wygasła",
            cost_points=10,
            stock_quantity=2,
            valid_until=timezone.localdate() - timedelta(days=1),
            is_active=True,
        )
        self.client.force_login(uzytkownik)

        odpowiedz = self.client.get(reverse("lista_nagrod"))

        nagrody = list(odpowiedz.context["nagrody"])
        self.assertIn(dostepna, nagrody)
        self.assertNotIn(bez_stanu, nagrody)
        self.assertNotIn(wygasla, nagrody)
        wygasla.refresh_from_db()
        self.assertFalse(wygasla.is_active)

    @patch("quiz.views.wyslij_email_z_nagroda", return_value=True)
    def test_odbior_nagrody_cyfrowej_aktualizuje_wszystkie_dane(self, mock_email):
        uzytkownik, profil = self.utworz_uzytkownika(punkty=100)
        nagroda = Reward.objects.create(
            name="Kod rabatowy",
            cost_points=30,
            stock_quantity=2,
            delivery_method="EMAIL",
            is_active=True,
        )
        self.client.force_login(uzytkownik)

        odpowiedz = self.client.post(reverse("odbierz_nagrode", args=[nagroda.id]))

        self.assertEqual(odpowiedz.status_code, 302)
        profil.refresh_from_db()
        nagroda.refresh_from_db()
        realizacja = RewardRedemption.objects.get(user=uzytkownik, reward=nagroda)
        self.assertEqual(profil.points, 70)
        self.assertEqual(nagroda.stock_quantity, 1)
        self.assertEqual(realizacja.cost_points, 30)
        self.assertEqual(realizacja.delivery_method, "EMAIL")
        self.assertTrue(realizacja.redemption_code.startswith("QA-"))
        self.assertEqual(realizacja.status, "SENT")
        self.assertIsNotNone(realizacja.email_sent_at)
        self.assertTrue(PointTransaction.objects.filter(user=uzytkownik, points=-30, transaction_type="reward").exists())
        mock_email.assert_called_once()

    @patch("quiz.views.wyslij_email_z_nagroda", return_value=False)
    def test_blad_emaila_nie_cofa_odebranej_nagrody_i_kodu(self, mock_email):
        uzytkownik, profil = self.utworz_uzytkownika(punkty=50)
        nagroda = Reward.objects.create(
            name="Kod cyfrowy",
            cost_points=20,
            stock_quantity=1,
            delivery_method="EMAIL",
            is_active=True,
        )
        self.client.force_login(uzytkownik)

        self.client.post(reverse("odbierz_nagrode", args=[nagroda.id]))

        profil.refresh_from_db()
        realizacja = RewardRedemption.objects.get(user=uzytkownik, reward=nagroda)
        self.assertEqual(profil.points, 30)
        self.assertEqual(realizacja.status, "EMAIL_FAILED")
        self.assertTrue(realizacja.redemption_code)

    def test_brak_punktow_blokuje_odbior_nagrody(self):
        uzytkownik, profil = self.utworz_uzytkownika(punkty=10)
        nagroda = Reward.objects.create(name="Za droga", cost_points=30, stock_quantity=2, is_active=True)
        self.client.force_login(uzytkownik)

        self.client.post(reverse("odbierz_nagrode", args=[nagroda.id]))

        profil.refresh_from_db()
        nagroda.refresh_from_db()
        self.assertEqual(profil.points, 10)
        self.assertEqual(nagroda.stock_quantity, 2)
        self.assertFalse(RewardRedemption.objects.exists())
        self.assertFalse(PointTransaction.objects.exists())

    def test_brak_stanu_blokuje_nagrode_i_ja_dezaktywuje(self):
        uzytkownik, profil = self.utworz_uzytkownika(punkty=100)
        nagroda = Reward.objects.create(name="Pusta", cost_points=20, stock_quantity=0, is_active=True)
        self.client.force_login(uzytkownik)

        self.client.post(reverse("odbierz_nagrode", args=[nagroda.id]))

        nagroda.refresh_from_db()
        profil.refresh_from_db()
        self.assertFalse(nagroda.is_active)
        self.assertEqual(profil.points, 100)
        self.assertFalse(RewardRedemption.objects.exists())

    def test_wygasla_nagroda_jest_blokowana(self):
        uzytkownik, profil = self.utworz_uzytkownika(punkty=100)
        nagroda = Reward.objects.create(
            name="Po terminie",
            cost_points=20,
            stock_quantity=2,
            valid_until=timezone.localdate() - timedelta(days=1),
            is_active=True,
        )
        self.client.force_login(uzytkownik)

        self.client.post(reverse("odbierz_nagrode", args=[nagroda.id]))

        nagroda.refresh_from_db()
        profil.refresh_from_db()
        self.assertFalse(nagroda.is_active)
        self.assertEqual(profil.points, 100)
        self.assertFalse(RewardRedemption.objects.exists())

    @patch("quiz.views.wyslij_email_z_nagroda", return_value=True)
    def test_ta_sama_nagrode_mozna_odebrac_wielokrotnie(self, mock_email):
        uzytkownik, profil = self.utworz_uzytkownika(punkty=100)
        nagroda = Reward.objects.create(
            name="Wielokrotna",
            cost_points=20,
            stock_quantity=3,
            delivery_method="EMAIL",
            is_active=True,
        )
        self.client.force_login(uzytkownik)

        self.client.post(reverse("odbierz_nagrode", args=[nagroda.id]))
        self.client.post(reverse("odbierz_nagrode", args=[nagroda.id]))

        profil.refresh_from_db()
        nagroda.refresh_from_db()
        realizacje = list(RewardRedemption.objects.filter(user=uzytkownik, reward=nagroda))
        self.assertEqual(len(realizacje), 2)
        self.assertNotEqual(realizacje[0].redemption_code, realizacje[1].redemption_code)
        self.assertEqual(profil.points, 60)
        self.assertEqual(nagroda.stock_quantity, 1)

    @patch("quiz.views.wyslij_email_z_nagroda", return_value=True)
    def test_historia_zachowuje_koszt_z_chwili_odbioru(self, mock_email):
        uzytkownik, profil = self.utworz_uzytkownika(punkty=100)
        nagroda = Reward.objects.create(name="Cena", cost_points=30, stock_quantity=2, is_active=True)
        self.client.force_login(uzytkownik)

        self.client.post(reverse("odbierz_nagrode", args=[nagroda.id]))
        realizacja = RewardRedemption.objects.get(user=uzytkownik, reward=nagroda)
        nagroda.cost_points = 50
        nagroda.save(update_fields=["cost_points"])
        realizacja.refresh_from_db()

        self.assertEqual(realizacja.cost_points, 30)

    @patch("quiz.views.wyslij_email_z_nagroda", return_value=True)
    def test_nagroda_fizyczna_wymaga_adresu_i_zmniejsza_saldo(self, mock_email):
        uzytkownik, profil = self.utworz_uzytkownika(punkty=100)
        nagroda = Reward.objects.create(
            name="Kubek",
            cost_points=40,
            stock_quantity=2,
            delivery_method="SHIPPING",
            is_active=True,
        )
        self.client.force_login(uzytkownik)

        odpowiedz = self.client.post(reverse("odbierz_nagrode", args=[nagroda.id]))

        profil.refresh_from_db()
        nagroda.refresh_from_db()
        realizacja = RewardRedemption.objects.get(user=uzytkownik, reward=nagroda)
        self.assertEqual(profil.points, 60)
        self.assertEqual(nagroda.stock_quantity, 1)
        self.assertEqual(realizacja.status, "ADDRESS_REQUIRED")
        self.assertEqual(realizacja.delivery_method, "SHIPPING")
        self.assertEqual(odpowiedz.url, reverse("adres_wysylki", args=[realizacja.id]))

    def test_zapis_i_edycja_adresu_nagrody_fizycznej(self):
        uzytkownik, profil = self.utworz_uzytkownika(punkty=100)
        nagroda = Reward.objects.create(name="Paczka", cost_points=20, stock_quantity=1, delivery_method="SHIPPING")
        realizacja = RewardRedemption.objects.create(
            user=uzytkownik,
            reward=nagroda,
            cost_points=20,
            delivery_method="SHIPPING",
            status="ADDRESS_REQUIRED",
        )
        self.client.force_login(uzytkownik)
        dane = {
            "shipping_first_name": "Jan",
            "shipping_last_name": "Kowalski",
            "shipping_street": "Testowa",
            "shipping_house_number": "10",
            "shipping_apartment_number": "2",
            "shipping_postal_code": "30-001",
            "shipping_city": "Kraków",
            "shipping_country": "Polska",
            "shipping_phone": "500600700",
        }

        odpowiedz = self.client.post(reverse("adres_wysylki", args=[realizacja.id]), dane)
        self.assertEqual(odpowiedz.status_code, 302)
        realizacja.refresh_from_db()
        self.assertEqual(realizacja.status, "READY_TO_SHIP")
        self.assertEqual(realizacja.shipping_city, "Kraków")
        self.assertIsNotNone(realizacja.shipping_address_submitted_at)

        dane["shipping_city"] = "Warszawa"
        self.client.post(reverse("adres_wysylki", args=[realizacja.id]), dane)
        realizacja.refresh_from_db()
        self.assertEqual(realizacja.shipping_city, "Warszawa")

    def test_adresu_nie_mozna_edytowac_po_wyslaniu(self):
        uzytkownik, profil = self.utworz_uzytkownika()
        nagroda = Reward.objects.create(name="Wysłana", cost_points=20, stock_quantity=1, delivery_method="SHIPPING")
        realizacja = RewardRedemption.objects.create(
            user=uzytkownik,
            reward=nagroda,
            cost_points=20,
            delivery_method="SHIPPING",
            status="SHIPPED",
            shipping_city="Kraków",
            shipped_at=timezone.now(),
        )
        self.client.force_login(uzytkownik)

        odpowiedz = self.client.get(reverse("adres_wysylki", args=[realizacja.id]))

        self.assertEqual(odpowiedz.status_code, 302)
        self.assertEqual(odpowiedz.url, reverse("historia_nagrod"))

    def test_uzytkownik_nie_ma_dostepu_do_adresu_innej_osoby(self):
        wlasciciel, profil = self.utworz_uzytkownika("wlasciciel", "wlasciciel@example.com")
        intruz, profil_intruza = self.utworz_uzytkownika("intruz", "intruz@example.com")
        nagroda = Reward.objects.create(name="Prywatna", cost_points=20, stock_quantity=1, delivery_method="SHIPPING")
        realizacja = RewardRedemption.objects.create(
            user=wlasciciel,
            reward=nagroda,
            cost_points=20,
            delivery_method="SHIPPING",
            status="ADDRESS_REQUIRED",
        )
        self.client.force_login(intruz)

        odpowiedz = self.client.get(reverse("adres_wysylki", args=[realizacja.id]))

        self.assertEqual(odpowiedz.status_code, 404)

    def test_odbior_nagrody_jest_atomowy(self):
        uzytkownik, profil = self.utworz_uzytkownika(punkty=100)
        nagroda = Reward.objects.create(name="Atomowa", cost_points=30, stock_quantity=2, is_active=True)
        self.client.force_login(uzytkownik)

        with patch("quiz.views.RewardRedemption.objects.create", side_effect=RuntimeError("test rollback")):
            with self.assertRaises(RuntimeError):
                self.client.post(reverse("odbierz_nagrode", args=[nagroda.id]))

        profil.refresh_from_db()
        nagroda.refresh_from_db()
        self.assertEqual(profil.points, 100)
        self.assertEqual(nagroda.stock_quantity, 2)
        self.assertEqual(PointTransaction.objects.count(), 0)
        self.assertEqual(RewardRedemption.objects.count(), 0)

    def test_generowany_kod_ma_oczekiwany_format_i_jest_unikalny(self):
        kod1 = generuj_kod_nagrody()
        RewardRedemption.objects.create(
            user=self.utworz_uzytkownika()[0],
            reward=Reward.objects.create(name="Kod", cost_points=1, stock_quantity=1),
            cost_points=1,
            redemption_code=kod1,
        )
        kod2 = generuj_kod_nagrody()

        self.assertRegex(kod1, r"^QA-[A-Z2-9]{4}-[A-Z2-9]{4}$")
        self.assertNotEqual(kod1, kod2)


class TestyAdministracji(BazaTestow):
    def _request_z_obsluga_wiadomosci(self, uzytkownik):
        request = RequestFactory().post("/admin/")
        request.user = uzytkownik
        middleware = SessionMiddleware(lambda req: None)
        middleware.process_request(request)
        request.session.save()
        request._messages = FallbackStorage(request)
        return request

    def test_admin_moze_recznie_wyzerowac_saldo_i_powstaje_transakcja(self):
        administrator = User.objects.create_superuser("admin", "admin@example.com", self.haslo)
        uzytkownik, profil = self.utworz_uzytkownika(punkty=75)
        request = self._request_z_obsluga_wiadomosci(administrator)
        model_admin = AdministracjaProfiliUzytkownikow(UserProfile, admin.site)

        model_admin.wyzeruj_punkty(request, UserProfile.objects.filter(id=profil.id))

        profil.refresh_from_db()
        self.assertEqual(profil.points, 0)
        transakcja = PointTransaction.objects.get(user=uzytkownik, transaction_type="reset")
        self.assertEqual(transakcja.points, -75)

    def test_pytanie_wymaga_dokladnie_jednej_poprawnej_odpowiedzi(self):
        quiz, pytania = self.utworz_quiz(liczba_pytan=1)
        pytanie = pytania[0][0]
        Answer.objects.filter(question=pytanie).delete()
        Fabryka = inlineformset_factory(
            Question,
            Answer,
            formset=ZestawFormularzyOdpowiedzi,
            fields=("text", "is_correct"),
            extra=0,
            can_delete=True,
        )

        dane_dwie_poprawne = {
            "answer_set-TOTAL_FORMS": "2",
            "answer_set-INITIAL_FORMS": "0",
            "answer_set-MIN_NUM_FORMS": "0",
            "answer_set-MAX_NUM_FORMS": "1000",
            "answer_set-0-text": "A",
            "answer_set-0-is_correct": "on",
            "answer_set-1-text": "B",
            "answer_set-1-is_correct": "on",
        }
        formularze = Fabryka(data=dane_dwie_poprawne, instance=pytanie, prefix="answer_set")
        self.assertFalse(formularze.is_valid())
        self.assertIn("dokładnie jedną poprawną", str(formularze.non_form_errors()))

        dane_jedna_poprawna = dane_dwie_poprawne.copy()
        dane_jedna_poprawna.pop("answer_set-1-is_correct")
        formularze = Fabryka(data=dane_jedna_poprawna, instance=pytanie, prefix="answer_set")
        self.assertTrue(formularze.is_valid())

    def test_admin_nie_pozwala_usuwac_quizow_i_nagrod(self):
        from .admin import AdministracjaNagrod, AdministracjaQuizow

        administrator = User.objects.create_superuser("admin2", "admin2@example.com", self.haslo)
        request = RequestFactory().get("/admin/")
        request.user = administrator

        admin_quizu = AdministracjaQuizow(Quiz, admin.site)
        admin_nagrody = AdministracjaNagrod(Reward, admin.site)

        self.assertFalse(admin_quizu.has_delete_permission(request))
        self.assertFalse(admin_nagrody.has_delete_permission(request))
