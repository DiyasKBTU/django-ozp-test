"""
Мерзімі өткен, бірақ аяқталмаған тест әрекеттерін аяқтайды (балл есептеледі).

Іске қосу: python manage.py finish_expired
Әрекет кез келген бетте ашылғанда өзі де аяқталады; бұл команда — cron үшін
(мысалы, 5 минут сайын), сонда студент бетті қайта ашпаса да нәтиже дұрыс көрінеді.
"""

from django.core.management.base import BaseCommand

from apps.quiz.services import finish_expired_attempts


class Command(BaseCommand):
    help = "Мерзімі өткен, бірақ аяқталмаған тест әрекеттерін аяқтайды."

    def handle(self, *args, **options):
        count = finish_expired_attempts()
        self.stdout.write(self.style.SUCCESS(f"Аяқталған әрекеттер: {count}"))
