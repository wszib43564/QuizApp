from django.urls import path
from . import views
urlpatterns = [
    path("", views.strona_glowna, name="strona_glowna"),
    path("rejestracja/", views.rejestracja, name="rejestracja"),
    path("logowanie/", views.logowanie, name="logowanie"),
    path("wylogowanie/", views.wylogowanie, name="wylogowanie"),
]
