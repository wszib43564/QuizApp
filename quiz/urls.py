from django.urls import path
from . import views
urlpatterns = [
    path("", views.strona_glowna, name="strona_glowna"),
    path("rejestracja/", views.rejestracja, name="rejestracja"),
    path("logowanie/", views.logowanie, name="logowanie"),
    path("wylogowanie/", views.wylogowanie, name="wylogowanie"),
    path("quizy/", views.lista_quizow, name="lista_quizow"),
    path("quizy/<int:id_quizu>/start/", views.rozpocznij_quiz, name="rozpocznij_quiz"),
    path("quizy/<int:id_quizu>/pytanie/", views.pytanie_quizu, name="pytanie_quizu"),
    path("quizy/<int:id_quizu>/wynik/<int:id_podejscia>/", views.wynik_quizu, name="wynik_quizu"),
    path("punkty/", views.punkty, name="punkty"),
    path("historia/", views.historia_quizow, name="historia_quizow"),
    path("nagrody/", views.lista_nagrod, name="lista_nagrod"),
    path("nagrody/<int:id_nagrody>/odbierz/", views.odbierz_nagrode, name="odbierz_nagrode"),
    path("historia-nagrod/", views.historia_nagrod, name="historia_nagrod"),
]
