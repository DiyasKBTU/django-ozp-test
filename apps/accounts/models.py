from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class StudyGroup(models.Model):
    """Студенттер тобы (мысалы, ИНФ-21); топ бір пәнге (мамандыққа) жатады."""

    name = models.CharField(_("атауы"), max_length=50, unique=True)
    subject = models.ForeignKey(
        "quiz.Subject",
        on_delete=models.PROTECT,
        related_name="groups",
        verbose_name=_("пән"),
    )

    class Meta:
        ordering = ["name"]
        verbose_name = _("топ")
        verbose_name_plural = _("топтар")

    def __str__(self):
        return self.name


class Profile(models.Model):
    """Қолданушының қосымша деректері: студенттің тобы, оқытушының пәндері."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
        verbose_name=_("қолданушы"),
    )
    group = models.ForeignKey(
        StudyGroup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="profiles",
        verbose_name=_("топ"),
    )
    # Оқытушыға тағайындалған пәндер (студентте бос)
    subjects = models.ManyToManyField(
        "quiz.Subject",
        blank=True,
        related_name="teacher_profiles",
        verbose_name=_("пәндер"),
    )

    class Meta:
        verbose_name = _("профиль")
        verbose_name_plural = _("профильдер")

    def __str__(self):
        return str(self.user)
