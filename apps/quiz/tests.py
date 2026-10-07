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
from django.utils.html import escape
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
from .services import bank_coverage


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
