from django.shortcuts import render

def strona_glowna(request):
    return render(request, "quiz/home.html")
