from django.contrib import admin
from .models import Answer, PointTransaction, Question, Quiz, QuizAttempt, Reward, RewardRedemption, UserProfile

admin.site.register(UserProfile)
admin.site.register(Quiz)
admin.site.register(Question)
admin.site.register(Answer)
admin.site.register(QuizAttempt)
admin.site.register(PointTransaction)
admin.site.register(Reward)
admin.site.register(RewardRedemption)
