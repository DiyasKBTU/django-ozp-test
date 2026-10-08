from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from django.forms.models import BaseInlineFormSet, construct_instance
from django.utils.translation import gettext_lazy as _

from apps.quiz.forms import add_bootstrap_classes

from .models import Profile, StudyGroup

# Django-ның қазақша аудармасында жоқ мәтіндер (ағылшынша шықпауы үшін)
USERNAME_LABEL = _("Логин")
PASSWORD_LABEL = _("Құпия сөз")


class RegisterForm(UserCreationForm):
    """Студентті тіркеу: аты, тегі, тобы, логин және құпия сөз."""

    first_name = forms.CharField(label=_("Аты"), max_length=150)
    last_name = forms.CharField(label=_("Тегі"), max_length=150)
    # Топтар белсенді пәндер бойынша топталып көрсетіледі: «МАТ-21 — Математика (Қазақша)»
    group = forms.ModelChoiceField(
        label=_("Тобы"),
        queryset=StudyGroup.objects.filter(subject__is_active=True)
        .select_related("subject")
        .order_by("subject__order", "name"),
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
        self.fields["group"].choices = self.group_choices()
        add_bootstrap_classes(self)

    def group_choices(self):
        """
        <optgroup> бойынша топталған тізім: [("", бос жол), (пән, [(id, «топ — пән (тіл)»), ...]), ...].
        Тіл көрсетіледі: топтың тесттері сол тілде өтеді.
        Тексеру бұрынғыдай queryset арқылы өтеді.
        """
        field = self.fields["group"]
        choices = [("", field.empty_label)]
        by_subject = {}
        for group in field.queryset:
            label = f"{group.name} — {group.subject.name} ({group.get_language_display()})"
            by_subject.setdefault(group.subject.name, []).append((group.pk, label))
        choices.extend(by_subject.items())
        return choices

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


class ProfileInlineFormSet(BaseInlineFormSet):
    """
    Admin-дегі профиль (топ, оқытушының пәндері). Жаңа қолданушы сақталғанда
    профильді post_save сигналы жасап қояды, сондықтан inline жаңа профиль
    жасамай, сол профильді толтырады (әйтпесе UNIQUE қатесі шығады).
    """

    def save_new(self, form, commit=True):
        profile = Profile.objects.filter(user=self.instance).first()
        if profile is None:
            return super().save_new(form, commit=commit)
        form.instance = construct_instance(form, profile)
        return form.save(commit=commit)
