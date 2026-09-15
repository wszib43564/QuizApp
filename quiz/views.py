from django.contrib.auth import login, logout
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST
from .forms import FormularzLogowania, FormularzRejestracji
from .models import UserProfile


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
