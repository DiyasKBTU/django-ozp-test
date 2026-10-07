from django.contrib.auth.models import User
from django.test import TestCase

from .models import Profile, StudyGroup


class ProfileTests(TestCase):
    def test_profile_created_for_new_user(self):
        user = User.objects.create_user(username="student", password="pass12345")
        self.assertTrue(Profile.objects.filter(user=user).exists())
        self.assertIsNone(user.profile.group)

    def test_profile_group(self):
        group = StudyGroup.objects.create(name="ИНФ-21")
        user = User.objects.create_user(username="student", password="pass12345")
        user.profile.group = group
        user.profile.save()
        self.assertEqual(group.profiles.get().user, user)
        self.assertEqual(str(group), "ИНФ-21")
