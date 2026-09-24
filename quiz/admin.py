from django.conf import settings
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.forms.models import BaseInlineFormSet
from django.utils import timezone

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

admin.site.site_header = "Quiz App - panel administratora"
admin.site.site_title = "Quiz App"
admin.site.index_title = "Zarządzanie aplikacją"


class ZestawFormularzyOdpowiedzi(BaseInlineFormSet):
    def clean(self):
        super().clean()

        if any(self.errors):
            return

        liczba_poprawnych = 0
        liczba_odpowiedzi_formularza = 0

        for formularz in self.forms:
            if not hasattr(formularz, "cleaned_data"):
                continue

            dane = formularz.cleaned_data

            if not dane or dane.get("DELETE"):
                continue

            if not dane.get("text"):
                continue

            liczba_odpowiedzi_formularza += 1

            if dane.get("is_correct"):
                liczba_poprawnych += 1

        if liczba_odpowiedzi_formularza == 0:
            raise ValidationError(
                "Pytanie musi posiadać przynajmniej jedną odpowiedź."
            )

        if liczba_poprawnych != 1:
            raise ValidationError(
                "Każde pytanie musi posiadać dokładnie jedną poprawną odpowiedź."
            )


class OdpowiedzInline(admin.TabularInline):
    model = Answer
    formset = ZestawFormularzyOdpowiedzi
    fields = ("text", "is_correct")
    extra = 4


class PytanieInline(admin.TabularInline):
    model = Question
    fields = ("text", "order", "time_limit_seconds")
    extra = 0
    ordering = ("order",)
    show_change_link = True
    can_delete = False


@admin.register(Quiz)
class AdministracjaQuizow(admin.ModelAdmin):
    list_display = (
        "title",
        "liczba_pytan",
        "time_limit_seconds",
        "expires_at",
        "status_dostepnosci",
        "is_active",
        "created_at",
    )
    list_editable = (
        "time_limit_seconds",
        "expires_at",
        "is_active",
    )
    list_filter = (
        "is_active",
        "expires_at",
        "created_at",
    )
    search_fields = ("title", "description")
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)
    save_on_top = True
    list_per_page = 30
    inlines = [PytanieInline]

    fieldsets = (
        (
            "Podstawowe informacje",
            {"fields": ("title", "description", "is_active")},
        ),
        (
            "Ustawienia quizu",
            {"fields": ("time_limit_seconds", "expires_at")},
        ),
        (
            "Informacje systemowe",
            {"fields": ("created_at",)},
        ),
    )

    actions = ["aktywuj_quizy", "dezaktywuj_quizy"]

    @admin.display(description="Liczba pytań")
    def liczba_pytan(self, obj):
        return obj.question_set.count()

    @admin.display(description="Status dostępności")
    def status_dostepnosci(self, obj):
        if not obj.is_active:
            return "Nieaktywny"

        if obj.expires_at and obj.expires_at <= timezone.now():
            return "Wygasł"

        return "Dostępny"

    @admin.action(description="Aktywuj wybrane quizy")
    def aktywuj_quizy(self, request, queryset):
        liczba = queryset.update(is_active=True)
        self.message_user(
            request,
            "Aktywowano quizy: " + str(liczba),
        )

    @admin.action(description="Dezaktywuj wybrane quizy")
    def dezaktywuj_quizy(self, request, queryset):
        liczba = queryset.update(is_active=False)
        self.message_user(
            request,
            "Dezaktywowano quizy: " + str(liczba),
        )

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Question)
class AdministracjaPytan(admin.ModelAdmin):
    list_display = (
        "skrocona_tresc",
        "quiz",
        "order",
        "time_limit_seconds",
        "liczba_odpowiedzi",
        "ma_jedna_poprawna_odpowiedz",
    )
    list_editable = ("order", "time_limit_seconds")
    list_filter = ("quiz",)
    search_fields = ("text", "quiz__title")
    ordering = ("quiz", "order")
    save_on_top = True
    list_per_page = 40
    inlines = [OdpowiedzInline]

    fieldsets = (
        (
            "Pytanie",
            {"fields": ("quiz", "text")},
        ),
        (
            "Ustawienia",
            {"fields": ("order", "time_limit_seconds")},
        ),
    )

    @admin.display(description="Treść pytania")
    def skrocona_tresc(self, obj):
        if len(obj.text) > 70:
            return obj.text[:70] + "..."
        return obj.text

    @admin.display(description="Odpowiedzi")
    def liczba_odpowiedzi(self, obj):
        return obj.answer_set.count()

    @admin.display(boolean=True, description="1 poprawna")
    def ma_jedna_poprawna_odpowiedz(self, obj):
        return obj.answer_set.filter(is_correct=True).count() == 1


@admin.register(UserProfile)
class AdministracjaProfiliUzytkownikow(admin.ModelAdmin):
    list_display = ("user", "email", "points")
    search_fields = ("user__username", "user__email")
    ordering = ("user__username",)
    list_per_page = 40
    actions = ["wyzeruj_punkty"]

    @admin.display(description="E-mail")
    def email(self, obj):
        return obj.user.email

    @admin.action(description="Wyzeruj punkty wybranych użytkowników")
    def wyzeruj_punkty(self, request, queryset):
        liczba_resetow = 0

        with transaction.atomic():
            profile_uzytkownikow = queryset.select_for_update()

            for profil in profile_uzytkownikow:
                if profil.points <= 0:
                    continue

                stare_punkty = profil.points
                profil.points = 0
                profil.save(update_fields=["points"])

                PointTransaction.objects.create(
                    user=profil.user,
                    points=-stare_punkty,
                    transaction_type="reset",
                    description="Reset punktów przez administratora",
                )
                liczba_resetow += 1

        self.message_user(
            request,
            "Wyzerowano punkty użytkowników: " + str(liczba_resetow),
        )


@admin.register(Reward)
class AdministracjaNagrod(admin.ModelAdmin):
    list_display = (
        "name",
        "cost_points",
        "stock_quantity",
        "delivery_method",
        "valid_until",
        "status_dostepnosci",
        "is_active",
    )
    list_editable = (
        "cost_points",
        "stock_quantity",
        "valid_until",
        "is_active",
    )
    list_filter = ("delivery_method", "is_active", "valid_until")
    search_fields = ("name", "description")
    ordering = ("cost_points",)
    save_on_top = True
    list_per_page = 30

    fieldsets = (
        (
            "Informacje o nagrodzie",
            {"fields": ("name", "description")},
        ),
        (
            "Koszt i dostępność",
            {
                "fields": (
                    "cost_points",
                    "stock_quantity",
                    "valid_until",
                    "delivery_method",
                    "is_active",
                )
            },
        ),
    )

    actions = ["aktywuj_nagrody", "dezaktywuj_nagrody"]

    @admin.display(description="Status")
    def status_dostepnosci(self, obj):
        if not obj.is_active:
            return "Nieaktywna"

        if obj.stock_quantity <= 0:
            return "Brak na stanie"

        if obj.valid_until and obj.valid_until < timezone.localdate():
            return "Po terminie"

        return "Dostępna"

    @admin.action(description="Aktywuj wybrane nagrody")
    def aktywuj_nagrody(self, request, queryset):
        liczba = queryset.update(is_active=True)
        self.message_user(
            request,
            "Aktywowano nagrody: " + str(liczba),
        )

    @admin.action(description="Dezaktywuj wybrane nagrody")
    def dezaktywuj_nagrody(self, request, queryset):
        liczba = queryset.update(is_active=False)
        self.message_user(
            request,
            "Dezaktywowano nagrody: " + str(liczba),
        )

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(QuizAttempt)
class AdministracjaPodejsc(admin.ModelAdmin):
    list_display = (
        "user",
        "quiz",
        "correct_answers",
        "incorrect_answers",
        "point_score",
        "balance_change",
        "status_punktowania",
        "finish_reason",
        "started_at",
        "completed_at",
    )
    list_filter = (
        "quiz",
        "is_rewarded_attempt",
        "finish_reason",
        "started_at",
        "completed_at",
    )
    search_fields = (
        "user__username",
        "user__email",
        "quiz__title",
    )
    ordering = ("-started_at",)
    date_hierarchy = "started_at"
    list_per_page = 50
    readonly_fields = (
        "user",
        "quiz",
        "started_at",
        "completed_at",
        "total_questions",
        "correct_answers",
        "incorrect_answers",
        "point_score",
        "balance_change",
        "is_rewarded_attempt",
        "finish_reason",
    )

    @admin.display(boolean=True, description="Punktowana")
    def status_punktowania(self, obj):
        return obj.is_rewarded_attempt

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PointTransaction)
class AdministracjaTransakcjiPunktowych(admin.ModelAdmin):
    list_display = (
        "user",
        "points",
        "transaction_type",
        "description",
        "created_at",
    )
    list_filter = ("transaction_type", "created_at")
    search_fields = (
        "user__username",
        "user__email",
        "description",
    )
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    list_per_page = 50
    readonly_fields = (
        "user",
        "points",
        "transaction_type",
        "description",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RewardRedemption)
class AdministracjaRealizacjiNagrod(admin.ModelAdmin):
    list_display = (
        "user",
        "reward",
        "delivery_method",
        "status",
        "cost_points",
        "tracking_number",
        "redeemed_at",
    )
    list_editable = ("tracking_number",)
    list_filter = (
        "delivery_method",
        "status",
        "reward",
        "redeemed_at",
    )
    search_fields = (
        "user__username",
        "user__email",
        "reward__name",
        "redemption_code",
        "tracking_number",
        "shipping_first_name",
        "shipping_last_name",
        "shipping_city",
    )
    ordering = ("-redeemed_at",)
    date_hierarchy = "redeemed_at"
    list_per_page = 50
    readonly_fields = (
        "user",
        "reward",
        "cost_points",
        "delivery_method",
        "redemption_code",
        "status",
        "redeemed_at",
        "email_sent_at",
        "shipping_first_name",
        "shipping_last_name",
        "shipping_street",
        "shipping_house_number",
        "shipping_apartment_number",
        "shipping_postal_code",
        "shipping_city",
        "shipping_country",
        "shipping_phone",
        "shipping_address_submitted_at",
        "shipped_at",
    )

    fieldsets = (
        (
            "Nagroda",
            {
                "fields": (
                    "user",
                    "reward",
                    "cost_points",
                    "delivery_method",
                    "status",
                    "redemption_code",
                    "redeemed_at",
                    "email_sent_at",
                )
            },
        ),
        (
            "Adres wysyłki",
            {
                "fields": (
                    "shipping_first_name",
                    "shipping_last_name",
                    "shipping_street",
                    "shipping_house_number",
                    "shipping_apartment_number",
                    "shipping_postal_code",
                    "shipping_city",
                    "shipping_country",
                    "shipping_phone",
                    "shipping_address_submitted_at",
                )
            },
        ),
        (
            "Przesyłka",
            {"fields": ("tracking_number", "shipped_at")},
        ),
    )

    actions = ["oznacz_jako_wyslane", "wyslij_ponownie_nagrode_cyfrowa"]

    @admin.action(description="Oznacz nagrody fizyczne jako wysłane")
    def oznacz_jako_wyslane(self, request, queryset):
        realizacje = queryset.filter(
            delivery_method="SHIPPING",
            status="READY_TO_SHIP",
        )

        liczba = 0

        for realizacja in realizacje:
            realizacja.status = "SHIPPED"
            realizacja.shipped_at = timezone.now()
            realizacja.save(
                update_fields=["status", "shipped_at"]
            )

            wiadomosc = (
                "Cześć "
                + realizacja.user.username
                + ',\n\nTwoja nagroda "'
                + realizacja.reward.name
                + '" została wysłana.'
            )

            if realizacja.tracking_number:
                wiadomosc += (
                    "\n\nNumer przesyłki:\n"
                    + realizacja.tracking_number
                )

            if realizacja.user.email:
                try:
                    send_mail(
                        subject="Quiz App - nagroda została wysłana",
                        message=wiadomosc,
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[realizacja.user.email],
                        using="default",
                    )
                except Exception:
                    pass

            liczba += 1

        self.message_user(
            request,
            "Oznaczono jako wysłane: " + str(liczba),
        )

    @admin.action(description="Wyślij ponownie nagrody cyfrowe e-mailem")
    def wyslij_ponownie_nagrode_cyfrowa(self, request, queryset):
        realizacje = queryset.filter(delivery_method="EMAIL")
        liczba = 0

        for realizacja in realizacje:
            if not realizacja.user.email:
                continue

            wiadomosc = (
                "Cześć "
                + realizacja.user.username
                + ",\n\nTwoja nagroda: "
                + realizacja.reward.name
                + "\n\nKod nagrody:\n"
                + str(realizacja.redemption_code)
            )

            try:
                wynik_wysylki = send_mail(
                    subject="Quiz App - Twoja nagroda: " + realizacja.reward.name,
                    message=wiadomosc,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[realizacja.user.email],
                    using="default",
                )

                if wynik_wysylki == 1:
                    realizacja.status = "SENT"
                    realizacja.email_sent_at = timezone.now()
                    realizacja.save(
                        update_fields=["status", "email_sent_at"]
                    )
                    liczba += 1
            except Exception:
                continue

        self.message_user(
            request,
            "Wysłano ponownie wiadomości: " + str(liczba),
        )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
