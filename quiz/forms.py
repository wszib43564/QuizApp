from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User

from .models import RewardRedemption


class FormularzRejestracji(UserCreationForm):
    email = forms.EmailField(required=True, label="Adres e-mail")

    class Meta:
        model = User
        fields = ["username", "email", "password1", "password2"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Nazwa użytkownika"
        self.fields["password1"].label = "Hasło"
        self.fields["password2"].label = "Powtórz hasło"
        for pole in self.fields.values():
            pole.widget.attrs["class"] = "form-control"


class FormularzLogowania(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Nazwa użytkownika"
        self.fields["password"].label = "Hasło"
        for pole in self.fields.values():
            pole.widget.attrs["class"] = "form-control"


class FormularzAdresuWysylki(forms.ModelForm):
    class Meta:
        model = RewardRedemption
        fields = [
            "shipping_first_name",
            "shipping_last_name",
            "shipping_street",
            "shipping_house_number",
            "shipping_apartment_number",
            "shipping_postal_code",
            "shipping_city",
            "shipping_country",
            "shipping_phone",
        ]
        labels = {
            "shipping_first_name": "Imię",
            "shipping_last_name": "Nazwisko",
            "shipping_street": "Ulica",
            "shipping_house_number": "Numer domu",
            "shipping_apartment_number": "Numer mieszkania",
            "shipping_postal_code": "Kod pocztowy",
            "shipping_city": "Miejscowość",
            "shipping_country": "Kraj",
            "shipping_phone": "Numer telefonu",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        pola_wymagane = [
            "shipping_first_name",
            "shipping_last_name",
            "shipping_street",
            "shipping_house_number",
            "shipping_postal_code",
            "shipping_city",
            "shipping_country",
            "shipping_phone",
        ]

        for nazwa, pole in self.fields.items():
            pole.widget.attrs["class"] = "form-control"
            if nazwa in pola_wymagane:
                pole.required = True
