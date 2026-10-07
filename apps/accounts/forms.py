from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _

from apps.quiz.forms import add_bootstrap_classes

from .models import StudyGroup

# Django-ның қазақша аудармасында жоқ мәтіндер (ағылшынша шықпауы үшін)
USERNAME_LABEL = _("Логин")
PASSWORD_LABEL = _("Құпия сөз")


class RegisterForm(UserCreationForm):
    """Студентті тіркеу: аты, тегі, тобы, логин және құпия сөз."""

    first_name = forms.CharField(label=_("Аты"), max_length=150)
    last_name = forms.CharField(label=_("Тегі"), max_length=150)
    group = forms.ModelChoiceField(
        label=_("Тобы"),
        queryset=StudyGroup.objects.all(),
        empty_label=_("— тізімнен таңдаңыз —"),
    )

    error_messages = {
        "password_mismatch": _("Екі құпия сөз бірдей емес."),
    }

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ["first_name", "last_name", "group", "username"]
        error_messages = {
            "username": {
                "unique": _("Бұл логин бос емес, басқасын таңдаңыз."),
                "invalid": _(
                    "Логинде тек әріптер, сандар және @ . + - _ белгілері болуы мүмкін."
                ),
            },
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = USERNAME_LABEL
        self.fields["username"].help_text = _(
            "150 таңбаға дейін: әріптер, сандар және @ . + - _ белгілері."
        )
        self.fields["password1"].label = PASSWORD_LABEL
        self.fields["password1"].help_text = (
            password_validation.password_validators_help_text_html()
        )
        self.fields["password2"].label = _("Құпия сөзді қайталаңыз")
        self.fields["password2"].help_text = ""
        add_bootstrap_classes(self)

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            # Профильді сигнал жасайды, бұл жерде тек топты жазамыз
            user.profile.group = self.cleaned_data["group"]
            user.profile.save()
        return user


class LoginForm(AuthenticationForm):
    """Django-ның дайын кіру формасы: қазақша мәтіндер және Bootstrap стилі."""

    error_messages = {
        "invalid_login": _("Логин немесе құпия сөз қате."),
        "inactive": _("Бұл тіркелгі бұғатталған."),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = USERNAME_LABEL
        self.fields["password"].label = PASSWORD_LABEL
        add_bootstrap_classes(self)
