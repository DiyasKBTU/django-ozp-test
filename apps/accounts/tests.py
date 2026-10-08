from datetime import timedelta
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.quiz.models import ExamSession, Subject

from .models import Profile, StudyGroup


def informatics():
    """Деректер миграциясы жасаған «Информатика» пәні."""
    return Subject.objects.get(code="informatics")


class ProfileTests(TestCase):
    def test_profile_created_for_new_user(self):
        user = User.objects.create_user(username="student", password="pass12345")
        self.assertTrue(Profile.objects.filter(user=user).exists())
        self.assertIsNone(user.profile.group)

    def test_profile_group(self):
        group = StudyGroup.objects.create(name="ИНФ-21", subject=informatics(), language="kk")
        user = User.objects.create_user(username="student", password="pass12345")
        user.profile.group = group
        user.profile.save()
        self.assertEqual(group.profiles.get().user, user)
        self.assertEqual(str(group), "ИНФ-21")


# ---------- 3-кезең: тіркелу, кіру, шығу ----------


class RegisterTests(TestCase):
    def setUp(self):
        self.group = StudyGroup.objects.create(name="ИНФ-21", subject=informatics(), language="kk")

    def register_data(self, **overrides):
        data = {
            "first_name": "Айгерім",
            "last_name": "Сапарова",
            "group": self.group.pk,
            "username": "aigerim",
            "password1": "Qazaq-Test-2026",
            "password2": "Qazaq-Test-2026",
        }
        data.update(overrides)
        return data

    def test_page_shows_groups(self):
        response = self.client.get(reverse("accounts:register"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ИНФ-21")

    def test_register_logs_in_and_redirects_to_dashboard(self):
        response = self.client.post(reverse("accounts:register"), self.register_data())
        self.assertRedirects(response, reverse("quiz:dashboard"))

        user = User.objects.get(username="aigerim")
        self.assertEqual(user.first_name, "Айгерім")
        self.assertEqual(user.last_name, "Сапарова")
        self.assertEqual(user.profile.group, self.group)
        self.assertFalse(user.is_staff)
        # Тіркелген соң бірден кірген
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_required_fields(self):
        for field in ["first_name", "last_name", "group", "username"]:
            with self.subTest(field=field):
                response = self.client.post(
                    reverse("accounts:register"), self.register_data(**{field: ""})
                )
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].has_error(field))
        self.assertFalse(User.objects.exists())

    def test_unknown_group_is_rejected(self):
        response = self.client.post(
            reverse("accounts:register"), self.register_data(group=self.group.pk + 100)
        )
        self.assertTrue(response.context["form"].has_error("group"))

    def test_passwords_must_match(self):
        response = self.client.post(
            reverse("accounts:register"), self.register_data(password2="Basqa-2026")
        )
        self.assertTrue(response.context["form"].has_error("password2"))
        self.assertFalse(User.objects.exists())

    def test_errors_are_in_kazakh(self):
        User.objects.create_user(username="busy", password="pass12345")
        cases = [
            ({"password1": "123", "password2": "123"}, "password2", "тым қысқа"),
            ({"password1": "12345678901", "password2": "12345678901"}, "password2", "тек сандардан"),
            ({"username": "busy"}, "username", "логин бос емес"),
            ({"username": "bad name!"}, "username", "тек әріптер"),
        ]
        for overrides, field, text in cases:
            with self.subTest(text=text):
                response = self.client.post(
                    reverse("accounts:register"), self.register_data(**overrides)
                )
                errors = " ".join(response.context["form"].errors[field])
                self.assertIn(text, errors)

    def test_page_has_no_english_django_texts(self):
        response = self.client.get(reverse("accounts:register"))
        self.assertContains(response, "Кемінде 8 таңба.")
        self.assertNotContains(response, "Your password")
        self.assertNotContains(response, "Required.")

    def test_logged_in_user_is_redirected(self):
        user = User.objects.create_user(username="student", password="pass12345")
        self.client.force_login(user)
        response = self.client.get(reverse("accounts:register"))
        self.assertRedirects(
            response, reverse("accounts:after_login"), target_status_code=302
        )


class LoginLogoutTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="student", password="pass12345")
        self.teacher = User.objects.create_user(
            username="teacher", password="pass12345", is_staff=True
        )
        self.teacher.profile.subjects.add(informatics())

    def login(self, username, next_url=None):
        url = reverse("accounts:login")
        if next_url:
            url += f"?next={next_url}"
        return self.client.post(url, {"username": username, "password": "pass12345"})

    def test_student_goes_to_dashboard(self):
        response = self.login("student")
        self.assertRedirects(response, reverse("accounts:after_login"), fetch_redirect_response=False)
        response = self.client.get(response["Location"])
        self.assertRedirects(response, reverse("quiz:dashboard"))

    def test_teacher_goes_to_questions(self):
        response = self.client.get(self.login("teacher")["Location"])
        self.assertRedirects(response, reverse("quiz:teacher_questions"))

    def test_next_parameter_is_respected(self):
        response = self.login("student", next_url=reverse("quiz:dashboard"))
        self.assertRedirects(response, reverse("quiz:dashboard"))

    def test_wrong_password(self):
        response = self.client.post(
            reverse("accounts:login"), {"username": "student", "password": "wrong"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Логин немесе құпия сөз қате.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_requires_post_and_goes_home(self):
        self.client.force_login(self.student)
        response = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(response, reverse("quiz:home"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_pages_open_in_russian(self):
        self.client.cookies["django_language"] = "ru"
        for url in [reverse("accounts:login"), reverse("accounts:register")]:
            with self.subTest(url=url):
                self.assertContains(self.client.get(url), 'lang="ru"')


class NavigationTests(TestCase):
    def test_guest_sees_login_and_register(self):
        response = self.client.get(reverse("quiz:home"))
        self.assertContains(response, reverse("accounts:login"))
        self.assertContains(response, reverse("accounts:register"))
        self.assertNotContains(response, reverse("accounts:logout"))

    def test_student_sees_dashboard_link(self):
        student = User.objects.create_user(username="student", password="pass12345")
        self.client.force_login(student)
        response = self.client.get(reverse("quiz:home"))
        self.assertContains(response, reverse("quiz:dashboard"))
        self.assertContains(response, reverse("accounts:logout"))
        self.assertNotContains(response, reverse("quiz:teacher_questions"))
        self.assertNotContains(response, reverse("admin:index"))

    def test_teacher_sees_teacher_links(self):
        teacher = User.objects.create_user(
            username="teacher", password="pass12345", is_staff=True
        )
        self.client.force_login(teacher)
        response = self.client.get(reverse("quiz:home"))
        for url_name in [
            "quiz:teacher_questions",
            "quiz:teacher_contexts",
            "quiz:teacher_bank",
            "admin:index",
            "accounts:logout",
        ]:
            with self.subTest(url_name=url_name):
                self.assertContains(response, reverse(url_name))
        self.assertNotContains(response, reverse("quiz:dashboard"))


# ---------- Оқытушыны қосу: тек admin арқылы ----------


class RegisterCannotCreateTeacherTests(TestCase):
    def test_register_ignores_staff_flags(self):
        group = StudyGroup.objects.create(name="ИНФ-21", subject=informatics(), language="kk")
        self.client.post(
            reverse("accounts:register"),
            {
                "first_name": "Айгерім",
                "last_name": "Сапарова",
                "group": group.pk,
                "username": "aigerim",
                "password1": "Qazaq-Test-2026",
                "password2": "Qazaq-Test-2026",
                "is_staff": "on",
                "is_superuser": "on",
            },
        )
        user = User.objects.get(username="aigerim")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.profile.subjects.exists())


class AdminAddTeacherTests(TestCase):
    """Әкімші оқытушыны admin-де бір бетте қосады: логин, аты-жөні, is_staff, пәндері."""

    def setUp(self):
        self.admin = User.objects.create_superuser(username="admin", password="pass12345")
        self.client.force_login(self.admin)
        self.subject = informatics()

    def add_user(self, **overrides):
        data = {
            "username": "teacher",
            "usable_password": "true",
            "password1": "Qazaq-Test-2026",
            "password2": "Qazaq-Test-2026",
            "first_name": "Ерлан",
            "last_name": "Серікұлы",
            "is_staff": "on",
            "profile-TOTAL_FORMS": "1",
            "profile-INITIAL_FORMS": "0",
            "profile-MIN_NUM_FORMS": "0",
            "profile-MAX_NUM_FORMS": "1",
            "profile-0-group": "",
            "profile-0-subjects": [self.subject.pk],
            "_save": "Save",
        }
        data.update(overrides)
        return self.client.post(reverse("admin:auth_user_add"), data)

    def test_add_page_has_teacher_fields(self):
        response = self.client.get(reverse("admin:auth_user_add"))
        self.assertContains(response, 'name="first_name"')
        self.assertContains(response, 'name="is_staff"')
        self.assertContains(response, 'name="profile-0-subjects"')

    def test_teacher_with_subject_in_one_step(self):
        response = self.add_user()
        self.assertEqual(response.status_code, 302)
        teacher = User.objects.get(username="teacher")
        self.assertTrue(teacher.is_staff)
        self.assertFalse(teacher.is_superuser)
        self.assertEqual(teacher.get_full_name(), "Ерлан Серікұлы")
        self.assertEqual(list(teacher.profile.subjects.all()), [self.subject])
        self.assertEqual(Profile.objects.filter(user=teacher).count(), 1)

        # Жаңа оқытушы кіріп, өз пәнінің беттерін көреді
        self.client.force_login(teacher)
        response = self.client.get(reverse("quiz:teacher_questions"))
        self.assertEqual(response.status_code, 200)

    def test_user_without_profile_changes(self):
        response = self.add_user(**{"profile-0-subjects": [], "is_staff": ""})
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username="teacher")
        self.assertFalse(user.is_staff)
        self.assertEqual(Profile.objects.filter(user=user).count(), 1)

    def test_warning_when_teacher_has_no_subject(self):
        response = self.add_user(**{"profile-0-subjects": []}, _save="")
        response = self.client.get(response["Location"])
        self.assertContains(response, "оған пән тағайындалмаған")

    def test_assign_subject_on_change_page(self):
        teacher = User.objects.create_user(username="old", password="pass12345", is_staff=True)
        url = reverse("admin:auth_user_change", args=[teacher.pk])
        data = {
            "username": "old",
            "first_name": "",
            "last_name": "",
            "email": "",
            "is_active": "on",
            "is_staff": "on",
            "last_login_0": "",
            "last_login_1": "",
            "date_joined_0": "2026-10-01",
            "date_joined_1": "10:00:00",
            "profile-TOTAL_FORMS": "1",
            "profile-INITIAL_FORMS": "1",
            "profile-MIN_NUM_FORMS": "0",
            "profile-MAX_NUM_FORMS": "1",
            "profile-0-id": teacher.profile.pk,
            "profile-0-user": teacher.pk,
            "profile-0-group": "",
            "profile-0-subjects": [self.subject.pk],
            "_save": "Save",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(list(teacher.profile.subjects.all()), [self.subject])


class TeacherAdminAccessTests(TestCase):
    """Оқытушы (is_staff) admin-де тек өз пәнінің сессиялары мен топтарын басқарады."""

    def setUp(self):
        call_command("load_subjects", stdout=StringIO())
        self.mathematics = Subject.objects.get(code="mathematics")
        self.teacher = User.objects.create_user(
            username="teacher", password="pass12345", is_staff=True
        )
        self.teacher.profile.subjects.add(self.mathematics)
        self.client.force_login(self.teacher)
        self.math_group = StudyGroup.objects.create(name="МАТ-21", subject=self.mathematics, language="kk")
        self.inf_group = StudyGroup.objects.create(name="ИНФ-21", subject=informatics(), language="kk")
        now = timezone.now()
        self.inf_session = ExamSession.objects.create(
            title="Информатика сессиясы",
            subject=informatics(),
            opens_at=now,
            closes_at=now + timedelta(hours=2),
        )

    def session_data(self, subject, *groups):
        today = timezone.localdate().strftime("%Y-%m-%d")
        return {
            "title": "Математика сессиясы",
            "subject": subject.pk,
            "opens_at_0": today,
            "opens_at_1": "09:00:00",
            "closes_at_0": today,
            "closes_at_1": "18:00:00",
            "groups": [group.pk for group in groups],
            "show_answers": ExamSession.ShowAnswers.AFTER_FINISH,
            "is_active": "on",
            "_save": "Save",
        }

    def test_teacher_can_create_session_for_own_subject(self):
        self.assertEqual(self.client.get(reverse("admin:quiz_examsession_add")).status_code, 200)
        response = self.client.post(
            reverse("admin:quiz_examsession_add"), self.session_data(self.mathematics, self.math_group)
        )
        self.assertEqual(response.status_code, 302)
        session = ExamSession.objects.get(title="Математика сессиясы")
        self.assertEqual(list(session.groups.all()), [self.math_group])

    def test_teacher_cannot_create_session_for_other_subject(self):
        response = self.client.post(
            reverse("admin:quiz_examsession_add"), self.session_data(informatics())
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("subject", response.context["adminform"].form.errors)
        response = self.client.post(
            reverse("admin:quiz_examsession_add"),
            self.session_data(self.mathematics, self.inf_group),
        )
        self.assertIn("groups", response.context["adminform"].form.errors)
        self.assertFalse(ExamSession.objects.filter(title="Математика сессиясы").exists())

    def test_teacher_sees_only_own_subject(self):
        response = self.client.get(reverse("admin:quiz_examsession_changelist"))
        self.assertNotContains(response, "Информатика сессиясы")
        response = self.client.get(reverse("admin:accounts_studygroup_changelist"))
        self.assertContains(response, "МАТ-21")
        self.assertNotContains(response, "ИНФ-21")
        url = reverse("admin:quiz_examsession_change", args=[self.inf_session.pk])
        # Бөтен жазба — admin оны «жоқ» деп, басты бетке қайтарады
        self.assertEqual(self.client.get(url).status_code, 302)

    def test_teacher_can_create_group(self):
        response = self.client.post(
            reverse("admin:accounts_studygroup_add"),
            {"name": "МАТ-22", "subject": self.mathematics.pk, "language": "ru", "_save": "Save"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(StudyGroup.objects.get(name="МАТ-22").language, "ru")

    def test_group_language_is_required(self):
        response = self.client.post(
            reverse("admin:accounts_studygroup_add"),
            {"name": "МАТ-23", "subject": self.mathematics.pk, "_save": "Save"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("language", response.context["adminform"].form.errors)
        self.assertFalse(StudyGroup.objects.filter(name="МАТ-23").exists())

    def test_teacher_cannot_manage_users_or_delete(self):
        forbidden = [
            reverse("admin:auth_user_changelist"),
            reverse("admin:auth_user_add"),
            reverse("admin:quiz_question_changelist"),
            reverse("admin:accounts_studygroup_delete", args=[self.math_group.pk]),
        ]
        for url in forbidden:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_admin_index_lists_sessions_and_groups(self):
        response = self.client.get(reverse("admin:index"))
        self.assertContains(response, reverse("admin:quiz_examsession_changelist"))
        self.assertContains(response, reverse("admin:accounts_studygroup_changelist"))
        self.assertNotContains(response, reverse("admin:auth_user_changelist"))
