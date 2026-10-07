from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class StudyGroup(models.Model):
    """Студенттер тобы (мысалы, ИНФ-21)."""

    name = models.CharField(_("атауы"), max_length=50, unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name = _("топ")
        verbose_name_plural = _("топтар")

    def __str__(self):
        return self.name


class Profile(models.Model):
    """Қолданушының қосымша деректері: қай топта оқиды."""

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

    class Meta:
        verbose_name = _("профиль")
        verbose_name_plural = _("профильдер")

    def __str__(self):
        return str(self.user)
