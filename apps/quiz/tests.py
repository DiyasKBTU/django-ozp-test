import random
from collections import Counter
from datetime import timedelta
from io import StringIO

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError
from django.forms import inlineformset_factory
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape
from django.utils.translation import override

from apps.accounts.models import StudyGroup

from .constants import (
    ANSWERS_PER_QUESTION,
    CONTEXTS_PER_TEST,
    LEVEL_QUOTA,
    MIN_CONTEXTS,
    MIN_QUESTIONS_PER_SUBTOPIC,
    QUESTIONS_PER_CONTEXT,
    QUESTIONS_TOTAL,
    SINGLE_QUESTIONS_PER_SUBTOPIC,
    SUBTOPICS_COUNT,
    TEST_DURATION_MINUTES,
)
from .forms import AnswerInlineFormSet
from .models import (
    LEVEL_FULL_DESCRIPTIONS,
    LEVEL_SHORT_DESCRIPTIONS,
    Answer,
    Attempt,
    AttemptQuestion,
    Context,
    ExamSession,
    Question,
    Subtopic,
    Topic,
)
from .services import (
    AttemptError,
    bank_coverage,
    build_variant,
    create_attempt,
    dashboard_sessions,
    split_duration,
    visible_sessions,
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


# ---------- 2-кезең: оқытушы беттері ----------


class TeacherTestCase(TestCase):
    """Оқытушы беттерінің ортақ дайындығы: тақырыптар және кірген оқытушы."""

    def setUp(self):
        run_command("load_topics")
        self.teacher = User.objects.create_user(
            username="teacher", password="pass12345", is_staff=True
        )
        self.client.force_login(self.teacher)
        self.topic = Topic.objects.get(number=2)
        self.subtopic = Subtopic.objects.get(number=3)  # 02 тақырыптікі

    def question_data(self, **overrides):
        """Сұрақ формасының дұрыс толтырылған POST деректері."""
        data = {
            "topic": self.topic.pk,
            "subtopic": self.subtopic.pk,
            "level": "B",
            "language": "kk",
            "context": "",
            "text": "Алғашқы электрондық есептеуіш машина қалай аталады?",
            "code": "",
            "answers-TOTAL_FORMS": "4",
            "answers-INITIAL_FORMS": "0",
            "answers-MIN_NUM_FORMS": "4",
            "answers-MAX_NUM_FORMS": "4",
            "answers-0-text": "ENIAC",
            "answers-1-text": "IBM PC",
            "answers-2-text": "Apple I",
            "answers-3-text": "Altair 8800",
            "answers-correct": "0",
            "save": "",
        }
        data.update(overrides)
        return data

    def create_question(self, **kwargs):
        """Дерекқорға 4 жауабы бар сұрақ жазады (бірінші жауап — дұрыс)."""
        data = {"subtopic": self.subtopic, "language": "kk", "text": "Сұрақ", "level": "A"}
        data.update(kwargs)
        question = Question.objects.create(**data)
        for index in range(ANSWERS_PER_QUESTION):
            Answer.objects.create(
                question=question, text=f"Жауап {index}", is_correct=index == 0
            )
        return question

    def create_context(self, language="kk"):
        return Context.objects.create(language=language, title="Кесте", text="Мәтін")


class TeacherAccessTests(TeacherTestCase):
    def teacher_urls(self):
        question = self.create_question()
        quiz_context = self.create_context()
        return [
            reverse("quiz:teacher_questions"),
            reverse("quiz:teacher_question_create"),
            reverse("quiz:teacher_question_edit", args=[question.pk]),
            reverse("quiz:teacher_contexts"),
            reverse("quiz:teacher_context_create"),
            reverse("quiz:teacher_context_edit", args=[quiz_context.pk]),
            reverse("quiz:teacher_bank"),
        ]

    def test_pages_open_for_teacher(self):
        for url in self.teacher_urls():
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_student_and_guest_are_redirected_to_login(self):
        urls = self.teacher_urls()
        student = User.objects.create_user(username="student", password="pass12345")
        for user in [student, None]:
            self.client.logout()
            if user:
                self.client.force_login(user)
            for url in urls:
                with self.subTest(url=url, user=user):
                    response = self.client.get(url)
                    self.assertEqual(response.status_code, 302)
                    self.assertIn(reverse("admin:login"), response["Location"])

    def test_pages_open_in_russian(self):
        self.client.cookies["django_language"] = "ru"
        for url in self.teacher_urls():
            with self.subTest(url=url):
                self.assertContains(self.client.get(url), 'lang="ru"')


class QuestionFormPageTests(TeacherTestCase):
    def post_question(self, url=None, **overrides):
        url = url or reverse("quiz:teacher_question_create")
        return self.client.post(url, self.question_data(**overrides))

    def test_create_question_with_answers(self):
        response = self.post_question(**{"answers-correct": "2"})
        question = Question.objects.get()
        self.assertRedirects(
            response, reverse("quiz:teacher_question_edit", args=[question.pk])
        )
        self.assertEqual(question.subtopic, self.subtopic)
        self.assertEqual(question.level, "B")
        self.assertFalse(question.is_demo)
        answers = list(question.answers.all())
        self.assertEqual(
            [answer.text for answer in answers],
            ["ENIAC", "IBM PC", "Apple I", "Altair 8800"],
        )
        self.assertEqual(
            [answer.is_correct for answer in answers], [False, False, True, False]
        )

    def test_subtopic_from_other_topic_is_rejected(self):
        other_subtopic = Subtopic.objects.get(number=5)  # 03 тақырыптікі
        response = self.post_question(subtopic=other_subtopic.pk)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Question.objects.exists())
        self.assertIn("subtopic", response.context["form"].errors)
        self.assertContains(response, "Бұл тақырыпша таңдалған тақырыпқа жатпайды.")

    def test_required_fields(self):
        for field in ["topic", "subtopic", "level", "language", "text"]:
            with self.subTest(field=field):
                response = self.post_question(**{field: ""})
                self.assertIn(field, response.context["form"].errors)
        self.assertFalse(Question.objects.exists())

    def test_code_and_image_are_optional(self):
        self.post_question(code="")
        question = Question.objects.get()
        self.assertEqual(question.code, "")
        self.assertFalse(question.image)

    def test_empty_answer_is_rejected(self):
        response = self.post_question(**{"answers-3-text": "   "})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Question.objects.exists())
        self.assertTrue(response.context["formset"].forms[3].errors)

    def test_correct_answer_is_required(self):
        data = self.question_data()
        del data["answers-correct"]
        response = self.client.post(reverse("quiz:teacher_question_create"), data)
        self.assertFalse(Question.objects.exists())
        self.assertContains(response, "Дұрыс жауапты белгілеңіз.")

    def test_more_than_4_answers_is_rejected(self):
        response = self.post_question(
            **{"answers-TOTAL_FORMS": "5", "answers-4-text": "Артық", "answers-correct": "4"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Question.objects.exists())

    def test_code_indentation_is_preserved(self):
        code = (
            "def f(n):\n"
            "    if n <= 1:\n"
            "        return 1\n"
            "    return n * f(n - 2)\n"
            "\n"
            'print(f(5), "end")'
        )
        # Бірінші жолдың шегінісі мен табуляция да сақталуы керек
        answer_code = '    if x > 0:\n\tprint("Иә")'
        # Браузер textarea мәтінін \r\n жол соңымен жібереді
        self.post_question(
            code=code.replace("\n", "\r\n"),
            **{"answers-1-text": answer_code.replace("\n", "\r\n")},
        )
        question = Question.objects.get()
        self.assertEqual(question.code, code)
        self.assertEqual(question.answers.all()[1].text, answer_code)

        # Алдын ала қарауда код <pre> ішінде өзгеріссіз көрсетіледі
        response = self.client.get(
            reverse("quiz:teacher_question_edit", args=[question.pk])
        )
        self.assertContains(response, f'<pre class="code-block">{escape(code)}</pre>')
        self.assertContains(
            response, f'<pre class="answer-text flex-grow-1">{escape(answer_code)}</pre>'
        )
        # Өңдеу формасының textarea өрісінде де шегіністер сақталады
        self.assertContains(response, f">\n{escape(code)}</textarea>")

    def test_save_and_next_keeps_selection(self):
        data = self.question_data(level="C", language="ru", save_and_next="")
        del data["save"]
        response = self.client.post(reverse("quiz:teacher_question_create"), data)
        expected = reverse("quiz:teacher_question_create") + (
            f"?topic={self.topic.pk}&subtopic={self.subtopic.pk}&level=C&language=ru"
        )
        self.assertRedirects(response, expected)

        form = self.client.get(expected).context["form"]
        self.assertEqual(form["topic"].value(), str(self.topic.pk))
        self.assertEqual(form["subtopic"].value(), str(self.subtopic.pk))
        self.assertEqual(form["level"].value(), "C")
        self.assertEqual(form["language"].value(), "ru")
        self.assertIsNone(form["text"].value())

    def test_edit_changes_only_correct_answer(self):
        question = self.create_question()
        answer_ids = list(question.answers.values_list("pk", flat=True))
        data = self.question_data(**{"answers-INITIAL_FORMS": "4", "answers-correct": "3"})
        for index, answer in enumerate(question.answers.all()):
            data[f"answers-{index}-id"] = answer.pk
            data[f"answers-{index}-text"] = answer.text
        url = reverse("quiz:teacher_question_edit", args=[question.pk])
        response = self.client.post(url, data)
        self.assertRedirects(response, url)
        answers = list(question.answers.all())
        self.assertEqual([answer.pk for answer in answers], answer_ids)
        self.assertEqual(
            [answer.is_correct for answer in answers], [False, False, False, True]
        )

    def test_edit_form_shows_topic_and_correct_answer(self):
        question = self.create_question(level="C")
        response = self.client.get(
            reverse("quiz:teacher_question_edit", args=[question.pk])
        )
        self.assertEqual(response.context["form"]["topic"].value(), self.topic.pk)
        self.assertEqual(response.context["formset"].correct_value(), "0")
        self.assertRegex(response.content.decode(), r'value="0"\s+checked')

    def test_subtopic_options_have_topic(self):
        response = self.client.get(reverse("quiz:teacher_question_create"))
        self.assertContains(
            response, f'<option value="{self.subtopic.pk}" data-topic="{self.topic.pk}">'
        )

    def test_level_shows_short_and_full_description(self):
        response = self.client.get(reverse("quiz:teacher_question_create"))
        for level in ["A", "B", "C"]:
            with self.subTest(level=level):
                self.assertContains(response, LEVEL_SHORT_DESCRIPTIONS[level])
                self.assertContains(response, f'title="{LEVEL_FULL_DESCRIPTIONS[level]}"')

    def test_context_language_must_match(self):
        quiz_context = self.create_context(language="ru")
        response = self.post_question(context=quiz_context.pk)
        self.assertFalse(Question.objects.exists())
        self.assertIn("context", response.context["form"].errors)

    def test_context_cannot_have_more_than_5_questions(self):
        quiz_context = self.create_context()
        for _ in range(QUESTIONS_PER_CONTEXT):
            self.create_question(context=quiz_context)
        response = self.post_question(context=quiz_context.pk)
        self.assertIn("context", response.context["form"].errors)
        self.assertEqual(quiz_context.questions.count(), QUESTIONS_PER_CONTEXT)

    def test_add_question_from_context_page(self):
        quiz_context = self.create_context(language="ru")
        url = reverse("quiz:teacher_question_create") + (
            f"?context={quiz_context.pk}&language=ru"
        )
        response = self.client.get(
            reverse("quiz:teacher_context_edit", args=[quiz_context.pk])
        )
        self.assertContains(response, url.replace("&", "&amp;"))

        form = self.client.get(url).context["form"]
        self.assertEqual(form["context"].value(), str(quiz_context.pk))
        self.assertEqual(form["language"].value(), "ru")

        # «Сақтап, келесісін қосу» контексті де сақтайды (онда әлі орын бар)
        response = self.post_question(
            language="ru", context=quiz_context.pk, save_and_next=""
        )
        self.assertEqual(quiz_context.questions.count(), 1)
        self.assertIn(f"context={quiz_context.pk}", response["Location"])


class QuestionListTests(TeacherTestCase):
    def setUp(self):
        super().setUp()
        self.question_a = self.create_question(text="Процессор жиілігі", level="A")
        self.question_b = self.create_question(
            text="Тізімді сұрыптау",
            level="B",
            language="ru",
            subtopic=Subtopic.objects.get(number=15),
            code="a.sort()",
        )

    def list_questions(self, **params):
        response = self.client.get(reverse("quiz:teacher_questions"), params)
        return list(response.context["page"].object_list)

    def test_filters(self):
        self.assertEqual(self.list_questions(), [self.question_a, self.question_b])
        self.assertEqual(self.list_questions(topic=self.topic.pk), [self.question_a])
        self.assertEqual(self.list_questions(subtopic=self.subtopic.pk), [self.question_a])
        self.assertEqual(self.list_questions(level="B"), [self.question_b])
        self.assertEqual(self.list_questions(language="ru"), [self.question_b])
        self.assertEqual(self.list_questions(q="Процессор"), [self.question_a])
        self.assertEqual(self.list_questions(q="sort"), [self.question_b])

    def test_copy_question(self):
        response = self.client.post(
            reverse("quiz:teacher_question_copy", args=[self.question_b.pk])
        )
        copy = Question.objects.latest("id")
        self.assertRedirects(response, reverse("quiz:teacher_question_edit", args=[copy.pk]))
        self.assertNotEqual(copy.pk, self.question_b.pk)
        self.assertEqual(
            (copy.subtopic, copy.text, copy.code, copy.level, copy.language),
            (self.question_b.subtopic, "Тізімді сұрыптау", "a.sort()", "B", "ru"),
        )
        self.assertEqual(
            list(copy.answers.values_list("text", "is_correct")),
            list(self.question_b.answers.values_list("text", "is_correct")),
        )

    def test_copy_of_full_context_question_becomes_single(self):
        quiz_context = self.create_context()
        questions = [
            self.create_question(context=quiz_context) for _ in range(QUESTIONS_PER_CONTEXT)
        ]
        self.client.post(reverse("quiz:teacher_question_copy", args=[questions[0].pk]))
        self.assertIsNone(Question.objects.latest("id").context)
        self.assertEqual(quiz_context.active_questions_count(), QUESTIONS_PER_CONTEXT)

    def test_toggle_active(self):
        url = reverse("quiz:teacher_question_toggle", args=[self.question_a.pk])
        next_url = reverse("quiz:teacher_questions") + "?level=A"
        response = self.client.post(url, {"next": next_url})
        self.assertRedirects(response, next_url)
        self.question_a.refresh_from_db()
        self.assertFalse(self.question_a.is_active)
        # Белсенді емес сұрақ жойылмайды және тізімде қалады
        self.assertIn(self.question_a, self.list_questions())

        # Бөтен сайтқа қайта бағыттамайды
        response = self.client.post(url, {"next": "https://evil.example.com/"})
        self.assertRedirects(response, reverse("quiz:teacher_questions"))
        self.question_a.refresh_from_db()
        self.assertTrue(self.question_a.is_active)

    def test_cannot_activate_question_in_full_context(self):
        quiz_context = self.create_context()
        inactive = self.create_question(context=quiz_context, is_active=False)
        for _ in range(QUESTIONS_PER_CONTEXT):
            self.create_question(context=quiz_context)
        self.client.post(reverse("quiz:teacher_question_toggle", args=[inactive.pk]))
        inactive.refresh_from_db()
        self.assertFalse(inactive.is_active)

    def test_copy_and_toggle_require_post(self):
        for name in ["quiz:teacher_question_copy", "quiz:teacher_question_toggle"]:
            with self.subTest(name=name):
                response = self.client.get(reverse(name, args=[self.question_a.pk]))
                self.assertEqual(response.status_code, 405)


class ContextPageTests(TeacherTestCase):
    def test_create_context_keeps_code(self):
        code = "for i in range(3):\n    print(i)"
        response = self.client.post(
            reverse("quiz:teacher_context_create"),
            {
                "title": "Цикл",
                "language": "kk",
                "text": "Программаны қараңыз.",
                "code": code.replace("\n", "\r\n"),
                "is_active": "on",
            },
        )
        quiz_context = Context.objects.get()
        self.assertRedirects(
            response, reverse("quiz:teacher_context_edit", args=[quiz_context.pk])
        )
        self.assertEqual(quiz_context.code, code)

    def test_context_page_shows_question_count(self):
        quiz_context = self.create_context()
        for _ in range(3):
            self.create_question(context=quiz_context)
        self.create_question(context=quiz_context, is_active=False)
        response = self.client.get(
            reverse("quiz:teacher_context_edit", args=[quiz_context.pk])
        )
        self.assertContains(response, "3 / 5")
        self.assertContains(self.client.get(reverse("quiz:teacher_contexts")), "3 / 5")

    def test_language_cannot_change_when_questions_linked(self):
        quiz_context = self.create_context()
        self.create_question(context=quiz_context)
        response = self.client.post(
            reverse("quiz:teacher_context_edit", args=[quiz_context.pk]),
            {"title": "Кесте", "language": "ru", "text": "Мәтін", "is_active": "on"},
        )
        self.assertIn("language", response.context["form"].errors)
        quiz_context.refresh_from_db()
        self.assertEqual(quiz_context.language, "kk")


class BankCoverageTests(TeacherTestCase):
    def test_counts_and_missing_cells(self):
        for level in ["A", "A", "B", "B", "B", "C"]:
            self.create_question(level=level)
        self.create_question(level="C", is_active=False)  # белсенді емес — саналмайды
        quiz_context = self.create_context()
        for _ in range(QUESTIONS_PER_CONTEXT):
            self.create_question(context=quiz_context)  # контекстік — бөлек саналады

        coverage = bank_coverage()
        row = next(row for row in coverage["rows"] if row["subtopic"] == self.subtopic)
        kk_cells, ru_cells = row["cells"][:4], row["cells"][4:]
        self.assertEqual([cell["count"] for cell in kk_cells], [2, 3, 1, 6])
        self.assertFalse(any(cell["missing"] for cell in kk_cells))
        self.assertEqual([cell["count"] for cell in ru_cells], [0, 0, 0, 0])
        self.assertTrue(all(cell["missing"] for cell in ru_cells))

        # Барлығы: kk бойынша A деңгейінде 2 сұрақ, квота 13 — жетіспейді
        self.assertEqual(coverage["totals"][0], {"count": 2, "missing": True, "is_total": False})
        self.assertEqual([item["count"] for item in coverage["contexts"]], [1, 0])
        self.assertTrue(coverage["contexts"][0]["missing"])

    def test_demo_bank_is_full(self):
        run_command("load_demo")
        coverage = bank_coverage()
        for row in coverage["rows"]:
            totals = [cell for cell in row["cells"] if cell["is_total"]]
            self.assertFalse(any(cell["missing"] for cell in totals), row["subtopic"])
        self.assertFalse(any(cell["missing"] for cell in coverage["totals"]))
        self.assertFalse(any(item["missing"] for item in coverage["contexts"]))

    def test_bank_page_marks_missing_in_red(self):
        response = self.client.get(reverse("quiz:teacher_bank"))
        # Бос банк: 20 тақырыпша × 8 ұяшық + қорытынды 8 ұяшық + 2 тілдің контексттері
        self.assertContains(response, 'class="missing', count=8 * SUBTOPICS_COUNT + 8 + 2)


# ---------- 3-кезең: студент кабинеті және сессиялар ----------


class StudentTestCase(TestCase):
    """Екі топ және ИНФ-21 тобындағы кірген студент."""

    def setUp(self):
        self.group = StudyGroup.objects.create(name="ИНФ-21")
        self.other_group = StudyGroup.objects.create(name="ИНФ-22")
        self.student = User.objects.create_user(username="student", password="pass12345")
        self.student.profile.group = self.group
        self.student.profile.save()
        self.client.force_login(self.student)

    def session_for(self, *groups, **kwargs):
        """Берілген топтарға (бос болса — барлығына) арналған сессия."""
        session = make_session(**kwargs)
        session.groups.set(groups)
        return session


class DashboardTests(StudentTestCase):
    def test_guest_is_redirected_to_login(self):
        self.client.logout()
        response = self.client.get(reverse("quiz:dashboard"))
        self.assertRedirects(
            response, f"{reverse('accounts:login')}?next={reverse('quiz:dashboard')}"
        )

    def test_only_own_group_and_all_groups_sessions_are_visible(self):
        own = self.session_for(self.group, title="Өз тобы")
        for_all = self.session_for(title="Барлығына")
        both = self.session_for(self.group, self.other_group, title="Екі топқа")
        self.session_for(self.other_group, title="Бөтен топ")
        self.session_for(self.group, title="Белсенді емес", is_active=False)

        self.assertCountEqual(visible_sessions(self.student), [own, for_all, both])

        response = self.client.get(reverse("quiz:dashboard"))
        self.assertContains(response, "Өз тобы")
        self.assertContains(response, "Барлығына")
        self.assertContains(response, "Екі топқа", count=1)
        self.assertNotContains(response, "Бөтен топ")
        self.assertNotContains(response, "Белсенді емес")

    def test_student_without_group_sees_only_sessions_for_all(self):
        for_all = self.session_for(title="Барлығына")
        self.session_for(self.group, title="Өз тобы")
        self.student.profile.group = None
        self.student.profile.save()
        self.assertEqual(list(visible_sessions(self.student)), [for_all])

    def test_open_close_boundaries(self):
        now = timezone.now()
        session = self.session_for(
            self.group, opens_at=now, closes_at=now + timedelta(hours=2)
        )
        second = timedelta(seconds=1)

        def list_name_at(moment):
            lists = dashboard_sessions(self.student, now=moment)
            for name in ["upcoming", "open", "past"]:
                if any(row["session"] == session for row in lists[name]):
                    return name
            return None

        self.assertEqual(list_name_at(session.opens_at - second), "upcoming")
        self.assertEqual(list_name_at(session.opens_at), "open")
        self.assertEqual(list_name_at(session.closes_at - second), "open")
        self.assertEqual(list_name_at(session.closes_at), "past")
        self.assertEqual(list_name_at(session.closes_at + second), "past")

    def test_three_lists_on_page(self):
        now = timezone.now()
        upcoming = self.session_for(
            self.group,
            opens_at=now + timedelta(days=2),
            closes_at=now + timedelta(days=2, hours=4),
        )
        open_now = self.session_for(self.group)
        past = self.session_for(
            self.group,
            opens_at=now - timedelta(days=2),
            closes_at=now - timedelta(days=1),
        )

        response = self.client.get(reverse("quiz:dashboard"))
        for name, session in [("upcoming", upcoming), ("open", open_now), ("past", past)]:
            with self.subTest(name=name):
                rows = response.context[name]
                self.assertEqual([row["session"] for row in rows], [session])
        # «Бастау» тек ашық сессияда
        self.assertContains(response, reverse("quiz:session_start", args=[open_now.pk]))
        self.assertNotContains(response, reverse("quiz:session_start", args=[upcoming.pk]))
        self.assertNotContains(response, reverse("quiz:session_start", args=[past.pk]))
        # Ашылуына қалған уақыт (тест кезінде бірнеше миллисекунд өтеді)
        self.assertContains(response, "Ашылуына қалды: 1 күн 23 сағ.")

    def test_split_duration(self):
        self.assertEqual(
            split_duration(timedelta(days=2, hours=3, minutes=15, seconds=59)),
            {"days": 2, "hours": 3, "minutes": 15},
        )
        self.assertEqual(
            split_duration(timedelta(minutes=45)), {"days": 0, "hours": 0, "minutes": 45}
        )

    def test_attempt_history_shows_only_own_attempts(self):
        session = self.session_for(self.group, title="Сессия-1")
        Attempt.objects.create(
            user=self.student,
            session=session,
            language="kk",
            deadline=session.closes_at,
            status=Attempt.Status.FINISHED,
            score=37,
        )
        other_student = User.objects.create_user(username="other", password="pass12345")
        other_session = self.session_for(title="Бөтен әрекет")
        Attempt.objects.create(
            user=other_student,
            session=other_session,
            language="ru",
            deadline=other_session.closes_at,
        )

        response = self.client.get(reverse("quiz:dashboard"))
        self.assertEqual(len(response.context["attempts"]), 1)
        self.assertContains(response, "37 / 50")
        self.assertContains(response, "Тапсырылды")
        # Тапсырылған сессияда «Бастау» батырмасы жоқ
        self.assertNotContains(response, reverse("quiz:session_start", args=[session.pk]))

    def test_dashboard_in_russian(self):
        self.client.cookies["django_language"] = "ru"
        self.assertContains(self.client.get(reverse("quiz:dashboard")), 'lang="ru"')


class SessionStartTests(StudentTestCase):
    def get(self, session):
        return self.client.get(reverse("quiz:session_start", args=[session.pk]))

    def test_own_session_opens(self):
        response = self.get(self.session_for(self.group))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["is_open"])

    def test_other_group_session_is_404(self):
        self.assertEqual(self.get(self.session_for(self.other_group)).status_code, 404)

    def test_inactive_session_is_404(self):
        self.assertEqual(self.get(self.session_for(is_active=False)).status_code, 404)

    def test_closed_session_is_not_open(self):
        now = timezone.now()
        session = self.session_for(opens_at=now - timedelta(hours=3), closes_at=now)
        self.assertFalse(self.get(session).context["is_open"])

    def test_guest_is_redirected_to_login(self):
        self.client.logout()
        response = self.get(self.session_for())
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])

    def test_student_cannot_open_teacher_pages(self):
        for url_name in ["teacher_questions", "teacher_contexts", "teacher_bank"]:
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(f"quiz:{url_name}"))
                # staff_member_required бетті көрсетпей, admin кіру бетіне жібереді
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("admin:login"), response["Location"])


# ---------- 4-кезең: нұсқа құру ----------


class VariantTestCase(TestCase):
    """Тақырыптар мен демо банк бір рет жүктеледі (әр тілде жеткілікті сұрақ)."""

    # Әр тексеруде бірнеше кездейсоқ нұсқа құрылады
    SEEDS = range(15)

    @classmethod
    def setUpTestData(cls):
        run_command("load_topics")
        run_command("load_demo")

    def variant_questions(self, language, seed):
        """Нұсқаны құрып, сұрақтарды тест ретімен қайтарады."""
        question_ids = build_variant(language, random.Random(seed))
        questions = Question.objects.select_related("subtopic").in_bulk(question_ids)
        return [questions[question_id] for question_id in question_ids]


class BuildVariantTests(VariantTestCase):
    def test_structure_matches_specification(self):
        single_count = SUBTOPICS_COUNT * SINGLE_QUESTIONS_PER_SUBTOPIC
        for language in ["kk", "ru"]:
            for seed in self.SEEDS:
                with self.subTest(language=language, seed=seed):
                    questions = self.variant_questions(language, seed)
                    singles = questions[:single_count]
                    context_part = questions[single_count:]

                    # 50 әртүрлі сұрақ, бәрі таңдалған тілде және белсенді
                    self.assertEqual(len(questions), QUESTIONS_TOTAL)
                    self.assertEqual(len({q.pk for q in questions}), QUESTIONS_TOTAL)
                    self.assertTrue(all(q.language == language for q in questions))
                    self.assertTrue(all(q.is_active for q in questions))

                    # 1–40: жеке сұрақтар, әр тақырыпшадан 2, тақырыпша ретімен
                    self.assertTrue(all(q.context_id is None for q in singles))
                    numbers = [q.subtopic.number for q in singles]
                    self.assertEqual(numbers, sorted(numbers))
                    self.assertEqual(
                        Counter(numbers),
                        {n: SINGLE_QUESTIONS_PER_SUBTOPIC for n in range(1, SUBTOPICS_COUNT + 1)},
                    )

                    # 41–50: 2 контекст × 5 сұрақ, әр контекстің сұрақтары қатар тұрады
                    blocks = [
                        context_part[i : i + QUESTIONS_PER_CONTEXT]
                        for i in range(0, len(context_part), QUESTIONS_PER_CONTEXT)
                    ]
                    self.assertEqual(len(blocks), CONTEXTS_PER_TEST)
                    context_ids = [block[0].context_id for block in blocks]
                    self.assertNotIn(None, context_ids)
                    self.assertEqual(len(set(context_ids)), CONTEXTS_PER_TEST)
                    for block in blocks:
                        self.assertEqual({q.context_id for q in block}, {block[0].context_id})

                    # Деңгейлер: A/B/C = 13/30/7
                    self.assertEqual(Counter(q.level for q in questions), LEVEL_QUOTA)

    def test_variants_are_random(self):
        first = {q.pk for q in self.variant_questions("kk", seed=1)}
        second = {q.pk for q in self.variant_questions("kk", seed=2)}
        self.assertNotEqual(first, second)

    def test_inactive_questions_and_contexts_are_never_chosen(self):
        # Әр тақырыпшадан бір B сұрақты және бір контекстті белсенді емес етеміз
        for subtopic in Subtopic.objects.all():
            question = subtopic.questions.filter(
                language="kk", context__isnull=True, level="B"
            ).first()
            question.is_active = False
            question.save()
        inactive_context = Context.objects.filter(language="kk").order_by("id").first()
        inactive_context.is_active = False
        inactive_context.save()

        inactive_ids = set(Question.objects.filter(is_active=False).values_list("id", flat=True))
        for seed in self.SEEDS:
            with self.subTest(seed=seed):
                questions = self.variant_questions("kk", seed)
                self.assertFalse({q.pk for q in questions} & inactive_ids)
                self.assertNotIn(inactive_context.pk, {q.context_id for q in questions})

    def test_rare_level_is_still_placed_exactly(self):
        """
        C деңгейлі жеке сұрақ тек 5 тақырыпшада қалса, квота (5) дәл толуы үшін
        сол бесеуінің әрқайсысынан C сұрақ алынуы керек (алмастыру қадамы).
        """
        singles = Question.objects.filter(language="kk", context__isnull=True, level="C")
        keep_subtopics = [1, 5, 9, 14, 20]
        singles.exclude(subtopic__number__in=keep_subtopics).update(is_active=False)
        for subtopic_number in keep_subtopics:
            extra = singles.filter(subtopic__number=subtopic_number, is_active=True)[1:]
            Question.objects.filter(pk__in=[q.pk for q in extra]).update(is_active=False)

        for seed in self.SEEDS:
            with self.subTest(seed=seed):
                questions = self.variant_questions("kk", seed)
                self.assertEqual(Counter(q.level for q in questions), LEVEL_QUOTA)
                c_singles = [q.subtopic.number for q in questions if q.level == "C" and not q.context_id]
                self.assertEqual(sorted(c_singles), keep_subtopics)

    def test_missing_level_falls_back_and_logs_warning(self):
        # Жеке C сұрақтар мүлде жоқ: басқа деңгей алынады, журналға ескерту жазылады
        Question.objects.filter(language="kk", context__isnull=True, level="C").update(
            is_active=False
        )
        with self.assertLogs("apps.quiz.services", level="WARNING") as logs:
            questions = self.variant_questions("kk", seed=3)
        self.assertIn("квотасына дәл сәйкес емес", logs.output[0])
        self.assertEqual(len(questions), QUESTIONS_TOTAL)
        numbers = Counter(q.subtopic.number for q in questions if not q.context_id)
        self.assertEqual(set(numbers.values()), {SINGLE_QUESTIONS_PER_SUBTOPIC})

    def test_not_enough_contexts(self):
        for context in Context.objects.filter(language="ru")[1:]:
            context.is_active = False
            context.save()
        with self.assertLogs("apps.quiz.services", level="WARNING"):
            with self.assertRaises(AttemptError):
                build_variant("ru")

    def test_context_with_inactive_question_is_not_used(self):
        # Бір сұрағы белсенді емес контекст толық емес (4 / 5) — тестке жарамайды
        broken = Context.objects.filter(language="ru").order_by("id").first()
        broken.questions.filter(pk=broken.questions.first().pk).update(is_active=False)
        for seed in self.SEEDS:
            with self.subTest(seed=seed):
                questions = self.variant_questions("ru", seed)
                self.assertNotIn(broken.pk, {q.context_id for q in questions})

    def test_subtopic_without_questions(self):
        Question.objects.filter(
            language="kk", context__isnull=True, subtopic__number=7
        ).update(is_active=False)
        with self.assertLogs("apps.quiz.services", level="WARNING"):
            with self.assertRaises(AttemptError):
                build_variant("kk")


class CreateAttemptTests(VariantTestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="student", password="pass12345")
        self.now = timezone.now()
        self.session = make_session(
            opens_at=self.now - timedelta(hours=1), closes_at=self.now + timedelta(hours=3)
        )

    def test_creates_50_questions_with_shuffled_answers(self):
        attempt = create_attempt(self.student, self.session, "ru", now=self.now, rng=random.Random(5))
        items = list(attempt.items.select_related("question"))
        self.assertEqual([item.order for item in items], list(range(1, QUESTIONS_TOTAL + 1)))
        self.assertEqual(attempt.language, "ru")
        self.assertEqual(attempt.status, Attempt.Status.IN_PROGRESS)
        self.assertTrue(all(item.question.language == "ru" for item in items))
        self.assertTrue(all(item.selected is None for item in items))

        sorted_orders = 0
        for item in items:
            answer_ids = list(item.question.answers.values_list("id", flat=True))
            # Нұсқалар реті — сол сұрақтың 4 жауабының алмастыруы
            self.assertEqual(sorted(item.answer_order), sorted(answer_ids))
            self.assertEqual(len(item.answer_order), ANSWERS_PER_QUESTION)
            sorted_orders += item.answer_order == sorted(answer_ids)
        # Реті араластырылған (50 сұрақтың бәрі өз ретімен қалуы мүмкін емес)
        self.assertLess(sorted_orders, QUESTIONS_TOTAL // 2)

    def test_deadline_is_125_minutes(self):
        attempt = create_attempt(self.student, self.session, "kk", now=self.now)
        self.assertEqual(attempt.started_at, self.now)
        self.assertEqual(attempt.deadline, self.now + timedelta(minutes=TEST_DURATION_MINUTES))

    def test_deadline_does_not_exceed_session_close(self):
        self.session.closes_at = self.now + timedelta(minutes=30)
        self.session.save()
        attempt = create_attempt(self.student, self.session, "kk", now=self.now)
        self.assertEqual(attempt.deadline, self.session.closes_at)

    def test_session_must_be_open(self):
        moments = [
            self.session.opens_at - timedelta(seconds=1),  # әлі ашылмаған
            self.session.closes_at,  # жабылды
            self.session.closes_at + timedelta(minutes=1),
        ]
        for moment in moments:
            with self.subTest(moment=moment):
                with self.assertRaises(AttemptError):
                    create_attempt(self.student, self.session, "kk", now=moment)
        # Ашылған сәтте бастауға болады
        create_attempt(self.student, self.session, "kk", now=self.session.opens_at)
        self.assertEqual(Attempt.objects.count(), 1)

    def test_inactive_session(self):
        self.session.is_active = False
        self.session.save()
        with self.assertRaises(AttemptError):
            create_attempt(self.student, self.session, "kk", now=self.now)

    def test_only_one_attempt_per_session(self):
        create_attempt(self.student, self.session, "kk", now=self.now)
        with self.assertRaises(AttemptError):
            create_attempt(self.student, self.session, "ru", now=self.now)
        self.assertEqual(Attempt.objects.count(), 1)
        self.assertEqual(AttemptQuestion.objects.count(), QUESTIONS_TOTAL)

    def test_nothing_saved_when_bank_is_incomplete(self):
        Context.objects.filter(language="kk").update(is_active=False)
        with self.assertLogs("apps.quiz.services", level="WARNING"):
            with self.assertRaises(AttemptError):
                create_attempt(self.student, self.session, "kk", now=self.now)
        self.assertFalse(Attempt.objects.exists())


class BankSampleTests(VariantTestCase):
    """Оқытушының «Үлгі нұсқа» беті: /teacher/bank/sample/?lang=..."""

    def setUp(self):
        self.teacher = User.objects.create_user(
            username="teacher", password="pass12345", is_staff=True
        )
        self.client.force_login(self.teacher)
        self.url = reverse("quiz:teacher_bank_sample")

    def get(self, lang=None):
        return self.client.get(self.url, {"lang": lang} if lang else {})

    def test_sample_for_each_language(self):
        for language in ["kk", "ru"]:
            with self.subTest(language=language):
                response = self.get(language)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["language"], language)
                summary = response.context["summary"]
                self.assertEqual(len(summary["questions"]), QUESTIONS_TOTAL)
                self.assertTrue(all(q.language == language for q in summary["questions"]))
                self.assertTrue(summary["all_ok"])
                self.assertEqual(
                    {item["level"]: item["count"] for item in summary["levels"]}, LEVEL_QUOTA
                )
                self.assertEqual(len(summary["subtopics"]), SUBTOPICS_COUNT)
                self.assertEqual(len(summary["contexts"]), CONTEXTS_PER_TEST)
                # 50 жолдық кесте: әр сұраққа бір жол (тақырып(ша) атауы жолда)
                self.assertContains(response, "<tr", count=QUESTIONS_TOTAL + 1)
                self.assertContains(response, "✓")

    def test_nothing_is_saved(self):
        self.get("kk")
        self.get("ru")
        self.assertFalse(Attempt.objects.exists())
        self.assertFalse(AttemptQuestion.objects.exists())

    def test_new_variant_on_every_reload(self):
        first = [q.pk for q in self.get("kk").context["summary"]["questions"]]
        second = [q.pk for q in self.get("kk").context["summary"]["questions"]]
        self.assertNotEqual(first, second)
        self.assertIn("no-cache", self.get("kk")["Cache-Control"])

    def test_unknown_or_missing_language_falls_back_to_kazakh(self):
        for lang in [None, "en", "x"]:
            with self.subTest(lang=lang):
                self.assertEqual(self.get(lang).context["language"], "kk")

    def test_bank_error_is_shown(self):
        Context.objects.filter(language="ru").update(is_active=False)
        with self.assertLogs("apps.quiz.services", level="WARNING"):
            response = self.get("ru")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("summary", response.context)
        self.assertContains(response, "Нұсқа құру мүмкін болмады")
        self.assertContains(response, "Банкте «Орысша» тіліндегі сұрақтар жеткіліксіз")

    def test_rule_violation_is_marked(self):
        # Жеке C сұрақтар жоқ: нұсқа құрылады, бірақ квота орындалмайды (✗)
        Question.objects.filter(language="kk", context__isnull=True, level="C").update(
            is_active=False
        )
        with self.assertLogs("apps.quiz.services", level="WARNING"):
            response = self.get("kk")
        summary = response.context["summary"]
        self.assertFalse(summary["all_ok"])
        self.assertFalse(summary["checks"]["levels"])
        self.assertTrue(summary["checks"]["subtopics"])
        self.assertTrue(summary["checks"]["contexts"])
        self.assertContains(response, "✗")

    def test_bank_page_has_sample_buttons(self):
        response = self.client.get(reverse("quiz:teacher_bank"))
        self.assertContains(response, f"{self.url}?lang=kk")
        self.assertContains(response, f"{self.url}?lang=ru")

    def test_student_cannot_open(self):
        student = User.objects.create_user(username="student", password="pass12345")
        self.client.force_login(student)
        response = self.get("kk")
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("admin:login"), response["Location"])

    def test_page_in_russian_interface(self):
        self.client.cookies["django_language"] = "ru"
        self.assertContains(self.get("kk"), "Образец варианта")


# ---------- Екі тіл ----------


class TranslationTests(StudentTestCase):
    """Тіл ауыстырғаннан кейін бет мәтіні орысшаға, қайта қазақшаға ауысады."""

    def switch_language(self, code):
        self.client.post(reverse("set_language"), {"language": code, "next": "/"})

    def test_dashboard_switches_language(self):
        self.switch_language("ru")
        response = self.client.get(reverse("quiz:dashboard"))
        self.assertContains(response, "Личный кабинет")
        self.assertContains(response, "Выйти")
        self.assertNotContains(response, "Жеке кабинет")

        self.switch_language("kk")
        response = self.client.get(reverse("quiz:dashboard"))
        self.assertContains(response, "Жеке кабинет")
        self.assertNotContains(response, "Личный кабинет")

    def test_pages_are_in_russian(self):
        self.client.logout()
        self.switch_language("ru")
        pages = {
            reverse("quiz:home"): "Подготовка к тесту ОЗП по информатике",
            reverse("accounts:login"): "Ещё не зарегистрированы?",
            reverse("accounts:register"): "Повторите пароль",
        }
        for url, text in pages.items():
            with self.subTest(url=url):
                self.assertContains(self.client.get(url), text)

        response = self.client.post(
            reverse("accounts:login"), {"username": "student", "password": "wrong"}
        )
        self.assertContains(response, "Неверный логин или пароль.")

    def test_teacher_pages_are_in_russian(self):
        run_command("load_topics")
        teacher = User.objects.create_user(
            username="teacher", password="pass12345", is_staff=True
        )
        self.client.force_login(teacher)
        self.switch_language("ru")
        pages = {
            reverse("quiz:teacher_questions"): "Новый вопрос",
            reverse("quiz:teacher_question_create"): "Сохранить и добавить следующий",
            reverse("quiz:teacher_contexts"): "Новый контекст",
            reverse("quiz:teacher_bank"): "Наполненность банка",
        }
        for url, text in pages.items():
            with self.subTest(url=url):
                self.assertContains(self.client.get(url), text)

    def test_russian_catalog_is_complete(self):
        """Орысша .po файлында аударылмаған жол қалмауы керек."""
        po_path = settings.BASE_DIR / "locale" / "ru" / "LC_MESSAGES" / "django.po"
        entries = po_path.read_text(encoding="utf-8").split("\n\n")[1:]
        # Аударылмаған жазба `msgstr ""` жолымен аяқталады (жалғасы жоқ)
        untranslated = [entry for entry in entries if entry.strip().endswith('msgstr ""')]
        self.assertEqual(untranslated, [])
        # makemessages ұқсас жолдан «болжап» қойған (fuzzy) аудармалар компиляцияланбайды
        fuzzy = [entry for entry in entries if "fuzzy" in entry]
        self.assertEqual(fuzzy, [])
