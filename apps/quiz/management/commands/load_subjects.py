"""
Пәндерді, тақырыптарды және тақырыпшаларды `apps/quiz/data/subjects.json`
файлынан жүктейді (TZ.md, 10.3).

Іске қосу:
    python manage.py load_subjects                     # барлық пән
    python manage.py load_subjects --only mathematics  # бір пән

Қайта іске қосуға болады: бар жазбалар жаңартылады, қайталанбайды.
Жүктеу алдында тексеріледі: әр пәнде дәл 20 тақырыпша, нөмірлері 1–20
қатарынан, атаулары бос емес. Қате болса, ештеңе жазылмайды.
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.quiz.constants import SUBTOPICS_COUNT
from apps.quiz.models import Subject, Subtopic, Topic

DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "subjects.json"


def read_subjects(path=DATA_FILE):
    """JSON файлынан пәндер тізімін оқиды."""
    with open(path, encoding="utf-8") as file:
        return json.load(file)["subjects"]


def find_errors(subject):
    """Бір пәннің деректеріндегі қателер тізімі (бос болса — дұрыс)."""
    code = subject.get("code") or "?"
    errors = []

    for field in ("code", "name_kk", "name_ru"):
        if not str(subject.get(field, "")).strip():
            errors.append(f"{code}: пәннің «{field}» өрісі бос.")
    duration = subject.get("duration_minutes")
    if not isinstance(duration, int) or duration <= 0:
        errors.append(f"{code}: duration_minutes оң бүтін сан болуы керек.")

    topic_numbers = []
    subtopic_numbers = []
    for topic in subject.get("topics", []):
        topic_numbers.append(topic.get("number"))
        for field in ("name_kk", "name_ru"):
            if not str(topic.get(field, "")).strip():
                errors.append(f"{code}: {topic.get('number')}-тақырыптың «{field}» атауы бос.")
        for subtopic in topic.get("subtopics", []):
            subtopic_numbers.append(subtopic.get("number"))
            for field in ("name_kk", "name_ru"):
                if not str(subtopic.get(field, "")).strip():
                    errors.append(
                        f"{code}: {subtopic.get('number')}-тақырыпшаның «{field}» атауы бос."
                    )

    if len(topic_numbers) != len(set(topic_numbers)):
        errors.append(f"{code}: тақырып нөмірлері қайталанады.")
    if len(subtopic_numbers) != SUBTOPICS_COUNT:
        errors.append(
            f"{code}: тақырыпша саны {len(subtopic_numbers)}, "
            f"керегі дәл {SUBTOPICS_COUNT}."
        )
    elif sorted(subtopic_numbers) != list(range(1, SUBTOPICS_COUNT + 1)):
        errors.append(f"{code}: тақырыпша нөмірлері 1–{SUBTOPICS_COUNT} қатарынан болуы керек.")
    return errors


class Command(BaseCommand):
    help = "Пәндерді, тақырыптарды, тақырыпшаларды subjects.json файлынан жүктейді"

    def add_arguments(self, parser):
        parser.add_argument(
            "--only", metavar="CODE", help="Тек осы пәнді жүктеу (мысалы, mathematics)."
        )

    def handle(self, *args, **options):
        subjects = read_subjects()
        # Реті файлдағы орны бойынша: 1, 2, 3, ...
        for order, subject in enumerate(subjects, start=1):
            subject["order"] = order

        if options["only"]:
            subjects = [subject for subject in subjects if subject.get("code") == options["only"]]
            if not subjects:
                raise CommandError(f"subjects.json ішінде «{options['only']}» пәні жоқ.")

        errors = []
        for subject in subjects:
            errors.extend(find_errors(subject))
        if errors:
            raise CommandError("Деректерде қате бар, ештеңе жазылмады:\n" + "\n".join(errors))

        self.save_subjects(subjects)

    @transaction.atomic
    def save_subjects(self, subjects):
        for data in subjects:
            subject, _ = Subject.objects.update_or_create(
                code=data["code"],
                defaults={
                    "name_kk": data["name_kk"],
                    "name_ru": data["name_ru"],
                    "duration_minutes": data["duration_minutes"],
                    "uses_formulas": data.get("uses_formulas", False),
                    "order": data["order"],
                },
            )
            topic_count = 0
            subtopic_count = 0

            for topic_data in data["topics"]:
                topic, _ = Topic.objects.update_or_create(
                    subject=subject,
                    number=topic_data["number"],
                    defaults={"name_kk": topic_data["name_kk"], "name_ru": topic_data["name_ru"]},
                )
                topic_count += 1

                for subtopic_data in topic_data["subtopics"]:
                    # Тақырыпша нөмірі пән ішінде бірегей: пән бойынша іздейміз
                    Subtopic.objects.update_or_create(
                        topic__subject=subject,
                        number=subtopic_data["number"],
                        defaults={
                            "topic": topic,
                            "name_kk": subtopic_data["name_kk"],
                            "name_ru": subtopic_data["name_ru"],
                            "description_kk": subtopic_data.get("description_kk", ""),
                        },
                    )
                    subtopic_count += 1

            self.stdout.write(
                self.style.SUCCESS(
                    f"{subject.code}: {topic_count} тақырып, {subtopic_count} тақырыпша, "
                    f"{subject.duration_minutes} мин."
                )
            )
