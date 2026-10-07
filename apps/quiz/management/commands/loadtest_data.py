"""
Жүктеме тестіне (loadtest/locustfile.py) керек деректер: тест аккаунттары
student001, student002, ... және солар үшін ғана ашық тест сессиясы.

Іске қосу:
    python manage.py loadtest_data                # 100 аккаунт: student001–student100
    python manage.py loadtest_data --count 1000   # 1000 аккаунт: student001–student1000
    python manage.py loadtest_data --delete       # аккаунттарды, сессияны, нәтижелерді өшіру

Қайта іске қосуға болады: аккаунттар қайталанбайды, олардың бұрынғы әрекеттері
өшіріледі, сессия қайта ашылады — тестті жаңадан тапсыруға болады.
Аккаунттар мен сессия бөлек «LOADTEST» тобына жатады: нақты студенттер
бұл сессияны көрмейді. Жүктеме тестінен кейін `--delete` орындаңыз.

Ескерту: тест нұсқасы құрылуы үшін банкте сұрақ жеткілікті болуы керек
(мысалы, `load_demo`).
"""

from datetime import timedelta

from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Profile, StudyGroup
from apps.quiz.constants import INFORMATICS_CODE
from apps.quiz.models import Attempt, ExamSession, Subject

GROUP_NAME = "LOADTEST"
SESSION_TITLE = "Жүктеме тесті (loadtest)"
USERNAME_PREFIX = "student"

# Тест аккаунттарының құпия сөзі (тек жүктеме тестіне; README-де де жазылған)
DEFAULT_PASSWORD = "loadtest-pass-2026"


def usernames(count):
    """student001, student002, ... (999-дан кейін: student1000, ...)."""
    return [f"{USERNAME_PREFIX}{number:03d}" for number in range(1, count + 1)]


class Command(BaseCommand):
    help = "Жүктеме тестіне арналған аккаунттар (student001...) мен ашық сессияны жасайды."

    def add_arguments(self, parser):
        parser.add_argument(
            "--count", type=int, default=100, help="Аккаунт саны (әдепкі: 100)."
        )
        parser.add_argument(
            "--password",
            default=DEFAULT_PASSWORD,
            help="Барлық аккаунттың құпия сөзі (locustfile-да да сол болуы керек).",
        )
        parser.add_argument(
            "--hours", type=int, default=3, help="Сессия неше сағат ашық тұрады (әдепкі: 3)."
        )
        parser.add_argument(
            "--delete", action="store_true", help="Жүктеме тестінің барлық деректерін өшіру."
        )

    def handle(self, *args, **options):
        if options["delete"]:
            self.delete_data()
            return
        if options["count"] < 1:
            raise CommandError("--count кемінде 1 болуы керек.")
        self.create_data(options["count"], options["password"], options["hours"])

    @transaction.atomic
    def create_data(self, count, password, hours):
        # Жүктеме тесті — информатика бойынша (--subject 12-кезеңде қосылады)
        subject = Subject.objects.filter(code=INFORMATICS_CODE).first()
        if subject is None:
            raise CommandError("Алдымен пәндерді жүктеңіз: python manage.py load_subjects")
        group, _created = StudyGroup.objects.get_or_create(
            name=GROUP_NAME, defaults={"subject": subject}
        )
        names = usernames(count)

        # Бөтен аккаунтты (нақты студент не оқытушы) кездейсоқ өзгертпеу үшін
        foreign = User.objects.filter(username__in=names).exclude(profile__group=group)
        if foreign.exists():
            raise CommandError(
                "Бұл логиндер бұрыннан бар және LOADTEST тобында емес: "
                + ", ".join(foreign.values_list("username", flat=True)[:10])
            )

        # Құпия сөз бір рет хэштеледі: 1000 аккаунтты әрқайсын бөлек хэштеу өте баяу
        password_hash = make_password(password)
        existing = set(User.objects.filter(username__in=names).values_list("username", flat=True))
        new_users = [
            User(username=name, first_name="Load", last_name=name, password=password_hash)
            for name in names
            if name not in existing
        ]
        # bulk_create сигнал жібермейді — профильдерді өзіміз жасаймыз
        User.objects.bulk_create(new_users)
        users = User.objects.filter(username__in=names)
        users.update(password=password_hash, is_active=True)
        Profile.objects.bulk_create(
            [
                Profile(user=user, group=group)
                for user in users.filter(profile__isnull=True)
            ]
        )

        now = timezone.now()
        session, _created = ExamSession.objects.update_or_create(
            title=SESSION_TITLE,
            defaults={
                "subject": group.subject,
                "opens_at": now - timedelta(minutes=1),
                "closes_at": now + timedelta(hours=hours),
                "show_answers": ExamSession.ShowAnswers.AFTER_FINISH,
                "is_active": True,
            },
        )
        session.groups.set([group])
        # Бір сессияда бір әрекет: қайта іске қосқанда бұрынғы әрекеттер өшіріледі
        old_attempts = Attempt.objects.filter(session=session)
        deleted = old_attempts.count()
        old_attempts.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"Дайын: {len(names)} аккаунт ({names[0]}–{names[-1]}), "
                f"жаңасы {len(new_users)}; өшірілген ескі әрекеттер: {deleted}."
            )
        )
        self.stdout.write(
            f"Сессия id={session.pk} «{session.title}», "
            f"{timezone.localtime(session.closes_at):%d.%m.%Y %H:%M} дейін ашық."
        )
        self.stdout.write(
            f"Locust үшін: LOADTEST_SESSION_ID={session.pk} LOADTEST_ACCOUNTS={count}"
        )

    @transaction.atomic
    def delete_data(self):
        group = StudyGroup.objects.filter(name=GROUP_NAME).first()
        session = ExamSession.objects.filter(title=SESSION_TITLE).first()
        attempts = 0
        if session:
            old_attempts = Attempt.objects.filter(session=session)
            attempts = old_attempts.count()
            old_attempts.delete()
            session.delete()
        users = 0
        if group:
            users = User.objects.filter(profile__group=group).count()
            # Пайдаланушымен бірге профилі мен басқа әрекеттері де өшеді (CASCADE)
            User.objects.filter(profile__group=group).delete()
            group.delete()
        self.stdout.write(
            self.style.SUCCESS(f"Өшірілді: {users} аккаунт, {attempts} әрекет және сессия.")
        )
