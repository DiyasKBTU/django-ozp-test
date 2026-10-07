"""
Информатиканың 11 тақырыбы мен 20 тақырыпшасын жүктейді (TZ.md, А қосымшасы).
Бұрынғы команда сақталған: `load_subjects --only informatics` деген сөз.

Іске қосу: python manage.py load_topics
Қайта іске қосуға болады: бар жазбалар жаңартылады, қайталанбайды.
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand

from apps.quiz.constants import INFORMATICS_CODE


class Command(BaseCommand):
    help = "Информатиканың тақырыптарын жүктейді (= load_subjects --only informatics)"

    def handle(self, *args, **options):
        call_command("load_subjects", only=INFORMATICS_CODE, stdout=self.stdout)
