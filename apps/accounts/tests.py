from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.quiz.models import Subject

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
        group = StudyGroup.objects.create(name="ИНФ-21", subject=informatics())
        user = User.objects.create_user(username="student", password="pass12345")
        user.profile.group = group
        user.profile.save()
        self.assertEqual(group.profiles.get().user, user)
        self.assertEqual(str(group), "ИНФ-21")


# ---------- 3-кезең: тіркелу, кіру, шығу ----------


class RegisterTests(TestCase):
    def setUp(self):
        self.group = StudyGroup.objects.create(name="ИНФ-21", subject=informatics())

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
