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
    order = models.IntegerField(default=1)
    time_limit_seconds = models.PositiveIntegerField(default=20)

    def __str__(self):
        return self.text


class Answer(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    text = models.CharField(max_length=300)
    is_correct = models.BooleanField(default=False)

    def __str__(self):
        return self.text


class QuizAttempt(models.Model):
    FINISH_REASONS = [
        ("COMPLETED", "Ukończony"),
        ("QUIZ_TIMEOUT", "Przekroczono czas quizu"),
    ]
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
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    cost_points = models.IntegerField(validators=[MinValueValidator(1)])
    stock_quantity = models.PositiveIntegerField(default=0)
    valid_until = models.DateField(null=True, blank=True, verbose_name="Ważna do")
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class RewardRedemption(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    reward = models.ForeignKey(Reward, on_delete=models.CASCADE)
    cost_points = models.PositiveIntegerField(default=0)
    redeemed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.user.username + " - " + self.reward.name
