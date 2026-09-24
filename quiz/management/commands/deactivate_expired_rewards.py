from django.core.management.base import BaseCommand
from django.utils import timezone
from quiz.models import Reward

class Command(BaseCommand):
    help = "Dezaktywuje nagrody, których termin ważności minął."

    def handle(self, *args, **options):
        dzisiaj = timezone.localdate()

        wygasle_nagrody = Reward.objects.filter(
            is_active=True,
            valid_until__isnull=False,
            valid_until__lt=dzisiaj,
        )

        liczba = wygasle_nagrody.count()
        wygasle_nagrody.update(is_active=False)

        self.stdout.write(
            self.style.SUCCESS(
                "Dezaktywowano wygasłe nagrody: " + str(liczba)
            )
        )
