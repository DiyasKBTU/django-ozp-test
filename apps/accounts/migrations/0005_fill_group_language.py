"""
Деректер миграциясы: бар топтардың оқыту тілін толтырады. Топ студенттері
бұрын тест тапсырса — көбірек тапсырылған тіл, әйтпесе қазақша (негізгі тіл).
Кейін әкімші/оқытушы admin-де түзете алады.
"""

from collections import Counter

from django.db import migrations


def fill_language(apps, schema_editor):
    StudyGroup = apps.get_model("accounts", "StudyGroup")
    Attempt = apps.get_model("quiz", "Attempt")

    for group in StudyGroup.objects.filter(language__isnull=True):
        languages = Counter(
            Attempt.objects.filter(user__profile__group=group).values_list("language", flat=True)
        )
        group.language = languages.most_common(1)[0][0] if languages else "kk"
        group.save(update_fields=["language"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_group_language"),
        ("quiz", "0005_answer_image"),
    ]

    operations = [
        migrations.RunPython(fill_language, migrations.RunPython.noop),
    ]
