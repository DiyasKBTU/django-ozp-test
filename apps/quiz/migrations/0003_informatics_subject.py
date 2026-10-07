"""
Деректер миграциясы (TZ.md, 10.2): «Информатика» пәнін жасайды және бұрынғы
барлық тақырыптарды, контексттерді, сессияларды, топтарды соған байлайды;
is_staff оқытушыларға «Информатика» тағайындалады. Ешбір жазба өшірілмейді.
"""

from django.conf import settings
from django.db import migrations

INFORMATICS = {
    "code": "informatics",
    "name_kk": "Информатика",
    "name_ru": "Информатика",
    "duration_minutes": 125,
    "uses_formulas": False,
    "order": 1,
}


def bind_to_informatics(apps, schema_editor):
    Subject = apps.get_model("quiz", "Subject")
    Topic = apps.get_model("quiz", "Topic")
    Context = apps.get_model("quiz", "Context")
    ExamSession = apps.get_model("quiz", "ExamSession")
    StudyGroup = apps.get_model("accounts", "StudyGroup")
    Profile = apps.get_model("accounts", "Profile")
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))

    defaults = {key: value for key, value in INFORMATICS.items() if key != "code"}
    subject, _created = Subject.objects.get_or_create(
        code=INFORMATICS["code"], defaults=defaults
    )

    # Пәні жоқ бұрынғы жазбалардың бәрі — информатикаға
    for model in (Topic, Context, ExamSession, StudyGroup):
        model.objects.filter(subject__isnull=True).update(subject=subject)

    # Оқытушылар (is_staff) — информатика оқытушылары
    for user in User.objects.filter(is_staff=True):
        profile, _created = Profile.objects.get_or_create(user=user)
        profile.subjects.add(subject)


class Migration(migrations.Migration):

    dependencies = [
        ("quiz", "0002_subject"),
        ("accounts", "0002_subject"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Кері бағытта ештеңе істелмейді: subject өрістері 0002 кері
        # миграциясымен бірге жойылады
        migrations.RunPython(bind_to_informatics, migrations.RunPython.noop),
    ]
