from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    points = models.IntegerField(default=0, validators=[MinValueValidator(0)])

    def __str__(self):
        return self.user.username


class Quiz(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    time_limit_seconds = models.PositiveIntegerField(default=300)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class Question(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE)
    text = models.TextField()
    order = models.PositiveIntegerField(default=1)
    time_limit_seconds = models.PositiveIntegerField(default=20)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.text


class Answer(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    text = models.CharField(max_length=300)
    is_correct = models.BooleanField(default=False)

    def __str__(self):
        return self.text


class QuizAttempt(models.Model):
    FINISH_REASONS = [("COMPLETED", "Ukończony"), ("QUIZ_TIMEOUT", "Przekroczono czas quizu")]
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE)
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    total_questions = models.PositiveIntegerField(default=0)
    correct_answers = models.PositiveIntegerField(default=0)
    incorrect_answers = models.PositiveIntegerField(default=0)
    point_score = models.IntegerField(default=0)
    balance_change = models.IntegerField(default=0)
    is_rewarded_attempt = models.BooleanField(default=False)
    finish_reason = models.CharField(max_length=30, choices=FINISH_REASONS, blank=True)

    def __str__(self):
        return self.user.username + " - " + self.quiz.title


class PointTransaction(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    points = models.IntegerField()
    transaction_type = models.CharField(max_length=50)
    description = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.user.username + " - " + str(self.points)


class Reward(models.Model):
    DELIVERY_CHOICES = [("EMAIL", "Nagroda cyfrowa - e-mail"), ("SHIPPING", "Nagroda fizyczna - wysyłka")]
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    cost_points = models.IntegerField(validators=[MinValueValidator(1)])
    stock_quantity = models.PositiveIntegerField(default=0)
    valid_until = models.DateField(null=True, blank=True, verbose_name="Ważna do")
    delivery_method = models.CharField(max_length=20, choices=DELIVERY_CHOICES, default="EMAIL", verbose_name="Sposób przekazania")
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class RewardRedemption(models.Model):
    STATUS_CHOICES = [
        ("EMAIL_PENDING", "Oczekuje na wysłanie e-maila"), ("SENT", "Wysłana e-mailem"),
        ("EMAIL_FAILED", "Błąd wysyłki e-maila"), ("ADDRESS_REQUIRED", "Oczekuje na adres"),
        ("READY_TO_SHIP", "Gotowa do wysyłki"), ("SHIPPED", "Wysłana"),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    reward = models.ForeignKey(Reward, on_delete=models.CASCADE)
    cost_points = models.PositiveIntegerField(default=0)
    delivery_method = models.CharField(max_length=20, choices=Reward.DELIVERY_CHOICES, default="EMAIL")
    redemption_code = models.CharField(max_length=20, unique=True, null=True, blank=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="EMAIL_PENDING")
    redeemed_at = models.DateTimeField(auto_now_add=True)
    email_sent_at = models.DateTimeField(null=True, blank=True)
    shipping_first_name = models.CharField(max_length=100, blank=True)
    shipping_last_name = models.CharField(max_length=100, blank=True)
    shipping_street = models.CharField(max_length=200, blank=True)
    shipping_house_number = models.CharField(max_length=30, blank=True)
    shipping_apartment_number = models.CharField(max_length=30, blank=True)
    shipping_postal_code = models.CharField(max_length=20, blank=True)
    shipping_city = models.CharField(max_length=100, blank=True)
    shipping_country = models.CharField(max_length=100, default="Polska", blank=True)
    shipping_phone = models.CharField(max_length=30, blank=True)
    shipping_address_submitted_at = models.DateTimeField(null=True, blank=True)
    tracking_number = models.CharField(max_length=100, blank=True)
    shipped_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.user.username + " - " + self.reward.name
