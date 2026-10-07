# QuizApp

Aplikacja umożliwia użytkownikom rozwiązywanie quizów, zdobywanie punktów za udzielone odpowiedzi oraz wymianę zgromadzonych punktów na nagrody. W projekcie wykorzystano mechanizmy grywalizacji, które mają uatrakcyjnić korzystanie z aplikacji i zachęcić użytkownika do regularnego rozwiązywania quizów.

## Funkcjonalności

Aplikacja oferuje między innymi:
- rejestrację i logowanie użytkowników,
- wylogowanie z konta,
- wyświetlanie dostępnych quizów,
- rozwiązywanie quizów pytanie po pytaniu,
- limit czasu dla pojedynczego pytania,
- limit czasu dla całego quizu,
- automatyczne zakończenie pytania lub quizu po upływie czasu,
- informację o poprawności udzielonej odpowiedzi,
- naliczanie punktów,
- rozróżnienie prób punktowanych i niepunktowanych,
- podsumowanie wyniku po zakończeniu quizu,
- historię rozwiązanych quizów,
- historię operacji punktowych,
- system nagród,
- wymianę punktów na nagrody,
- obsługę nagród cyfrowych wysyłanych przez e-mail,
- obsługę nagród fizycznych wymagających podania adresu wysyłki,
- historię odebranych nagród,
- kontrolę dostępności i liczby sztuk nagród,
- obsługę terminów ważności quizów i nagród,
- panel administracyjny do zarządzania danymi aplikacji.

## Technologie

Projekt został wykonany przy użyciu:
- Python
- Django 6.1.1
- HTML
- CSS
- JavaScript
- Bootstrap 5.3.8
- SQLite

## Struktura projektu

Najważniejsze elementy projektu:

```text
QuizApp/
├── config/
│   ├── __init__.py
│   ├── asgi.py
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
│
├── quiz/
│   ├── management/
│   ├── migrations/
│   ├── static/
│   ├── templates/
│   ├── __init__.py
│   ├── admin.py
│   ├── apps.py
│   ├── forms.py
│   ├── models.py
│   ├── tests.py
│   ├── urls.py
│   └── views.py
│
├── .gitignore
├── manage.py
├── requirements.txt
└── README.md
```

Folder `config` zawiera główną konfigurację projektu Django.
Folder `quiz` zawiera logikę aplikacji, modele danych, widoki, formularze, testy, szablony HTML oraz pliki statyczne.

## Uruchomienie projektu

Instrukcja dotyczy systemu Windows i programu PowerShell.

## 1. Pobranie repozytorium

```powershell
git clone https://github.com/wszib43564/QuizApp.git
cd QuizApp
```

## 2. Sprawdzenie Pythona

```powershell
python --version
```
Jeżeli polecenie wyświetli numer wersji Pythona, można przejść dalej.

## 3. Utworzenie środowiska wirtualnego

```powershell
python -m venv .venv
```
Jeżeli folder `.venv` już istnieje, ten krok można pominąć.

## 4. Aktywacja środowiska wirtualnego

```powershell
.venv\Scripts\Activate.ps1
```
Po poprawnej aktywacji na początku wiersza poleceń powinno pojawić się:

```text
(.venv)
```

### Błąd „running scripts is disabled on this system”

Jeżeli PowerShell zablokuje uruchomienie pliku `Activate.ps1`, należy w tym samym oknie wykonać:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```
Jeżeli pojawi się pytanie o potwierdzenie, należy je zatwierdzić.

Następnie ponownie uruchomić:

```powershell
.venv\Scripts\Activate.ps1
```
Ustawienie `-Scope Process` obowiązuje wyłącznie w aktualnym oknie PowerShell i po jego zamknięciu zostaje cofnięte.

## 5. Instalacja wymaganych bibliotek

```powershell
pip install -r requirements.txt
```

## 6. Przygotowanie bazy danych

```powershell
python manage.py migrate
```

## 7. Utworzenie konta administratora

Ten krok jest opcjonalny, ale pozwala korzystać z panelu administracyjnego Django.

```powershell
python manage.py createsuperuser
```

## 8. Uruchomienie aplikacji

```powershell
python manage.py runserver
```

Po uruchomieniu aplikacja będzie dostępna pod adresem:

```text
http://127.0.0.1:8000/
```

Panel administracyjny:

```text
http://127.0.0.1:8000/admin/
```

## 9. Zatrzymanie serwera

Aby zatrzymać serwer, należy w PowerShellu nacisnąć:

```text
Ctrl + C
```

## Kolejne uruchomienie projektu

Przy kolejnym uruchomieniu nie trzeba ponownie tworzyć środowiska ani instalować wszystkich bibliotek.

Wystarczy:

```powershell
cd QuizApp
.venv\Scripts\Activate.ps1
python manage.py runserver
```

Jeżeli PowerShell ponownie zablokuje aktywację środowiska:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.venv\Scripts\Activate.ps1
python manage.py runserver
```

## Testy

Projekt posiada testy automatyczne.

```powershell
python manage.py test
```

## Obsługa wiadomości e-mail

Domyślnie projekt korzysta z trybu konsolowego, dlatego podczas pracy lokalnej wiadomości e-mail są wyświetlane w terminalu zamiast być rzeczywiście wysyłane.
Projekt umożliwia również skonfigurowanie wysyłki wiadomości za pomocą serwera SMTP.