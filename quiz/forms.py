from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User


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
