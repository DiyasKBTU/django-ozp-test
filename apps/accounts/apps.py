from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    verbose_name = _("Қолданушылар мен топтар")

    def ready(self):
        # Сигналдарды тіркеу (жаңа қолданушыға профиль жасау)
        from . import signals  # noqa: F401
