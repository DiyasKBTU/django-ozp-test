from collections import Counter
from datetime import timedelta
from io import StringIO

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError
from django.forms import inlineformset_factory
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import override

from .constants import (
    ANSWERS_PER_QUESTION,
    LEVEL_QUOTA,
    MIN_CONTEXTS,
    MIN_QUESTIONS_PER_SUBTOPIC,
    QUESTIONS_PER_CONTEXT,
    SUBTOPICS_COUNT,
)
from .forms import AnswerInlineFormSet
from .models import (
    Answer,
    Attempt,
    AttemptQuestion,
    Context,
    ExamSession,
    Question,
    Subtopic,
    Topic,
)


def run_command(*args):
    """Команданы шығысын жасырып іске қосады."""
    call_command(*args, stdout=StringIO())


def make_session(**kwargs):
    now = timezone.now()
    data = {
        "title": "Сынақ сессия",
        "opens_at": now - timedelta(hours=1),
        "closes_at": now + timedelta(hours=3),
    }
    data.update(kwargs)
    return ExamSession.objects.create(**data)


class LoadTopicsTests(TestCase):
    def test_loads_11_topics_and_20_subtopics(self):
        run_command("load_topics")
        self.assertEqual(Topic.objects.count(), 11)
        self.assertEqual(Subtopic.objects.count(), SUBTOPICS_COUNT)

    def test_is_idempotent(self):
        run_command("load_topics")
        run_command("load_topics")
        self.assertEqual(Topic.objects.count(), 11)
        self.assertEqual(Subtopic.objects.count(), SUBTOPICS_COUNT)

    def test_subtopics_belong_to_correct_topics(self):
        run_command("load_topics")
        topic_2 = Topic.objects.get(number=2)
        self.assertEqual(list(topic_2.subtopics.values_list("number", flat=True)), [3, 4])
        topic_8 = Topic.objects.get(number=8)
        self.assertEqual(
            list(topic_8.subtopics.values_list("number", flat=True)), [13, 14, 15, 16]
        )

    def test_name_follows_interface_language(self):
        run_command("load_topics")
        topic = Topic.objects.get(number=3)
        with override("kk"):
            self.assertEqual(topic.name, "Логикалық операциялар")
            self.assertEqual(str(topic), "03 Логикалық операциялар")
        with override("ru"):
            self.assertEqual(topic.name, "Логические операции")


class LoadDemoTests(TestCase):
    def setUp(self):
        run_command("load_topics")
        run_command("load_demo")

    def test_requires_topics(self):
        Question.objects.all().delete()
        Context.objects.all().delete()
        Subtopic.objects.all().delete()
        with self.assertRaises(CommandError):
            run_command("load_demo")

    def test_all_demo_data_is_marked(self):
        self.assertFalse(Question.objects.filter(is_demo=False).exists())
        self.assertFalse(Context.objects.filter(is_demo=False).exists())

    def test_every_question_has_4_answers_and_one_correct(self):
        for question in Question.objects.prefetch_related("answers"):
            answers = list(question.answers.all())
            self.assertEqual(len(answers), ANSWERS_PER_QUESTION)
            self.assertEqual(sum(answer.is_correct for answer in answers), 1)

    def test_bank_is_big_enough_for_each_language(self):
        for language in ["kk", "ru"]:
            single = Question.objects.filter(
                language=language, context__isnull=True, is_active=True
            )
            per_subtopic = Counter(single.values_list("subtopic__number", flat=True))
            self.assertEqual(len(per_subtopic), SUBTOPICS_COUNT)
            self.assertGreaterEqual(min(per_subtopic.values()), MIN_QUESTIONS_PER_SUBTOPIC)

            # Әр деңгейдің сұрақтары квотадан кем емес
            per_level = Counter(single.values_list("level", flat=True))
            for level, quota in LEVEL_QUOTA.items():
                self.assertGreaterEqual(per_level[level], quota)

            contexts = Context.objects.filter(language=language, is_active=True)
            self.assertGreaterEqual(contexts.count(), MIN_CONTEXTS)
            for context in contexts:
                questions = context.questions.all()
                self.assertEqual(questions.count(), QUESTIONS_PER_CONTEXT)
                self.assertFalse(questions.exclude(language=language).exists())

    def test_code_indentation_is_preserved(self):
        question = Question.objects.filter(code__contains="return n * f(n - 2)").first()
        self.assertIn("\n    if n <= 1:\n        return 1\n", question.code)
        answer = Answer.objects.filter(text__startswith="if x % 2 == 0:").first()
        self.assertEqual(answer.text, 'if x % 2 == 0:\n    print("Yes")')

    def test_second_run_does_not_duplicate(self):
        count = Question.objects.count()
        run_command("load_demo")
        self.assertEqual(Question.objects.count(), count)

    def test_delete_removes_only_demo_data(self):
        real_question = Question.objects.create(
            subtopic=Subtopic.objects.get(number=1),
            language="kk",
            text="Нақты сұрақ",
            level="A",
        )
        # Демо сұрақ кездесетін тест әрекеті де өшуі керек
        user = User.objects.create_user(username="student", password="pass12345")
        session = make_session()
        attempt = Attempt.objects.create(
            user=user, session=session, language="kk", deadline=session.closes_at
        )
        demo_question = Question.objects.filter(is_demo=True).first()
        AttemptQuestion.objects.create(attempt=attempt, question=demo_question, order=1)

        run_command("load_demo", "--delete")

        self.assertFalse(Question.objects.filter(is_demo=True).exists())
        self.assertFalse(Context.objects.filter(is_demo=True).exists())
        self.assertFalse(Attempt.objects.exists())
        self.assertEqual(list(Question.objects.all()), [real_question])
        self.assertEqual(Answer.objects.count(), 0)


class ModelTests(TestCase):
    def setUp(self):
        run_command("load_topics")
        self.subtopic = Subtopic.objects.get(number=5)

    def test_attempt_is_unique_per_user_and_session(self):
        user = User.objects.create_user(username="student", password="pass12345")
        session = make_session()
        Attempt.objects.create(user=user, session=session, language="kk", deadline=session.closes_at)
        with self.assertRaises(IntegrityError):
            Attempt.objects.create(
                user=user, session=session, language="ru", deadline=session.closes_at
            )

    def test_session_must_close_after_opening(self):
        now = timezone.now()
        session = ExamSession(title="Қате", opens_at=now, closes_at=now - timedelta(hours=1))
        with self.assertRaises(ValidationError):
            session.full_clean()

    def test_context_question_language_must_match(self):
        context = Context.objects.create(language="ru", title="Контекст", text="Мәтін")
        question = Question(
            subtopic=self.subtopic, context=context, language="kk", text="Сұрақ", level="B"
        )
        with self.assertRaises(ValidationError):
            question.full_clean()


class AnswerFormSetTests(TestCase):
    """Дәл 4 нұсқа және дәл бір дұрыс жауап тексерісі."""

    def setUp(self):
        run_command("load_topics")
        self.question = Question.objects.create(
            subtopic=Subtopic.objects.get(number=1), language="kk", text="Сұрақ", level="A"
        )
        self.formset_class = inlineformset_factory(
            Question,
            Answer,
            formset=AnswerInlineFormSet,
            fields=["text", "is_correct"],
            extra=ANSWERS_PER_QUESTION,
        )

    def make_formset(self, answers):
        """answers: [(мәтін, дұрыс па), ...] — бос жолдар толтырылмайды."""
        data = {
            "answers-TOTAL_FORMS": str(ANSWERS_PER_QUESTION),
            "answers-INITIAL_FORMS": "0",
        }
        for index, (text, is_correct) in enumerate(answers):
            data[f"answers-{index}-text"] = text
            if is_correct:
                data[f"answers-{index}-is_correct"] = "on"
        return self.formset_class(data, instance=self.question, prefix="answers")

    def test_valid_with_4_answers_and_one_correct(self):
        formset = self.make_formset([("1", True), ("2", False), ("3", False), ("4", False)])
        self.assertTrue(formset.is_valid(), formset.non_form_errors())

    def test_invalid_with_3_answers(self):
        formset = self.make_formset([("1", True), ("2", False), ("3", False)])
        self.assertFalse(formset.is_valid())

    def test_invalid_with_two_correct(self):
        formset = self.make_formset([("1", True), ("2", True), ("3", False), ("4", False)])
        self.assertFalse(formset.is_valid())

    def test_invalid_without_correct(self):
        formset = self.make_formset([("1", False), ("2", False), ("3", False), ("4", False)])
        self.assertFalse(formset.is_valid())


class PageTests(TestCase):
    def test_home_page_in_kazakh_by_default(self):
        response = self.client.get(reverse("quiz:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'lang="kk"')
        self.assertContains(response, "ПББ тестіне дайындық")

    def test_language_switch_is_saved(self):
        response = self.client.post(
            reverse("set_language"), {"language": "ru", "next": "/"}
        )
        self.assertRedirects(response, "/")
        response = self.client.get(reverse("quiz:home"))
        self.assertContains(response, 'lang="ru"')

    def test_admin_pages_open_for_superuser(self):
        run_command("load_topics")
        run_command("load_demo")
        admin = User.objects.create_superuser(username="admin", password="pass12345")
        self.client.force_login(admin)
        question = Question.objects.first()
        urls = [
            reverse("admin:index"),
            reverse("admin:quiz_topic_changelist"),
            reverse("admin:quiz_subtopic_changelist"),
            reverse("admin:quiz_question_changelist"),
            reverse("admin:quiz_question_add"),
            reverse("admin:quiz_question_change", args=[question.pk]),
            reverse("admin:quiz_context_changelist"),
            reverse("admin:quiz_examsession_changelist"),
            reverse("admin:quiz_examsession_add"),
            reverse("admin:quiz_attempt_changelist"),
            reverse("admin:accounts_studygroup_changelist"),
            reverse("admin:auth_user_changelist"),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
