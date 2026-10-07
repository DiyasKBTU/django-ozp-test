"""
Бизнес-логика (TZ.md, 3–4-бөлімдер): сұрақты сақтау және көшіру, банк толуы,
студентке көрінетін сессиялар.
Нұсқа құру мен балл есептеу кейінгі кезеңдерде осында қосылады.
"""

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from .constants import (
    LEVEL_QUOTA,
    MIN_CONTEXTS,
    MIN_QUESTIONS_PER_SUBTOPIC,
    QUESTIONS_PER_CONTEXT,
)
from .models import Answer, Context, ExamSession, Language, Level, Question, Subtopic


# ---------- Сұрақтар ----------


@transaction.atomic
def save_question(form, formset):
    """Сұрақты және оның 4 жауап нұсқасын бірге сақтайды (формалар тексерілген)."""
    question = form.save()
    formset.instance = question
    formset.save()
    return question


def context_has_room(context):
    """Контекстте жаңа белсенді сұраққа орын бар ма (5-тен аз)."""
    return context.active_questions_count() < QUESTIONS_PER_CONTEXT


@transaction.atomic
def copy_question(question):
    """
    Сұрақтың көшірмесін жауаптарымен бірге жасайды.
    Контекст толып қалса (5 сұрақ), көшірме жеке сұрақ болады.
    """
    context = question.context
    if context and not context_has_room(context):
        context = None

    copy = Question.objects.create(
        subtopic=question.subtopic,
        context=context,
        language=question.language,
        text=question.text,
        image=question.image,
        code=question.code,
        level=question.level,
        is_demo=question.is_demo,
    )
    for answer in question.answers.all():
        Answer.objects.create(question=copy, text=answer.text, is_correct=answer.is_correct)
    return copy


def toggle_question_active(question):
    """
    Сұрақты «белсенді емес» етеді немесе қайта белсендіреді (сұрақ жойылмайды,
    сондықтан ескі нәтижелер бұзылмайды). Контекст толып қалса, сұрақ
    белсендірілмейді — онда False қайтарады.
    """
    if not question.is_active and question.context and not context_has_room(question.context):
        return False
    question.is_active = not question.is_active
    question.save(update_fields=["is_active"])
    return True


# ---------- Банк толуы ----------


def bank_coverage():
    """
    Банк толуы: әр тақырыпша × тіл × деңгей бойынша белсенді жеке сұрақтар саны.

    Жетіспейтін жерлер `missing=True` деп белгіленеді:
    - деңгей ұяшығы — сұрақ мүлде жоқ болса;
    - тақырыпша жиыны — MIN_QUESTIONS_PER_SUBTOPIC-тен (6) аз болса;
    - деңгей бойынша жалпы сан — LEVEL_QUOTA-дан (13/30/7) аз болса;
    - толық контексттер (5 белсенді сұрақ) — MIN_CONTEXTS-тен (4) аз болса.
    """
    languages = Language.values
    levels = Level.values

    # (тақырыпша id, тіл, деңгей) → сұрақ саны
    counts = {}
    grouped = (
        Question.objects.filter(is_active=True, context__isnull=True)
        .values("subtopic_id", "language", "level")
        .annotate(total=Count("id"))
    )
    for row in grouped:
        counts[(row["subtopic_id"], row["language"], row["level"])] = row["total"]

    # Кесте жолдары: ұяшықтар реті — kk: A, B, C, Σ, ru: A, B, C, Σ
    rows = []
    level_totals = {(language, level): 0 for language in languages for level in levels}
    for subtopic in Subtopic.objects.select_related("topic"):
        cells = []
        for language in languages:
            subtopic_total = 0
            for level in levels:
                count = counts.get((subtopic.pk, language, level), 0)
                cells.append({"count": count, "missing": count == 0, "is_total": False})
                subtopic_total += count
                level_totals[(language, level)] += count
            cells.append(
                {
                    "count": subtopic_total,
                    "missing": subtopic_total < MIN_QUESTIONS_PER_SUBTOPIC,
                    "is_total": True,
                }
            )
        rows.append({"subtopic": subtopic, "cells": cells})

    # Қорытынды жол: деңгей бойынша жалпы сан квотамен салыстырылады
    totals = []
    for language in languages:
        language_total = 0
        for level in levels:
            count = level_totals[(language, level)]
            totals.append(
                {"count": count, "missing": count < LEVEL_QUOTA[level], "is_total": False}
            )
            language_total += count
        totals.append(
            {
                "count": language_total,
                "missing": language_total < MIN_QUESTIONS_PER_SUBTOPIC * len(rows),
                "is_total": True,
            }
        )

    # Тестке тек 5 белсенді сұрағы бар (толық) контекст жарайды
    full_contexts = (
        Context.objects.filter(is_active=True)
        .annotate(active_count=Count("questions", filter=Q(questions__is_active=True)))
        .filter(active_count=QUESTIONS_PER_CONTEXT)
    )
    contexts = []
    for language, label in Language.choices:
        count = full_contexts.filter(language=language).count()
        contexts.append(
            {"label": label, "count": count, "missing": count < MIN_CONTEXTS}
        )

    return {
        "languages": Language.choices,
        "levels": levels,
        "rows": rows,
        "totals": totals,
        "contexts": contexts,
        "level_quota": LEVEL_QUOTA,
        "min_questions": MIN_QUESTIONS_PER_SUBTOPIC,
        "min_contexts": MIN_CONTEXTS,
        "questions_per_context": QUESTIONS_PER_CONTEXT,
    }


# ---------- Студентке арналған сессиялар ----------


def visible_sessions(user):
    """
    Студентке көрінетін белсенді сессиялар: оның тобына арналғандары
    және топтары бос (барлығына арналған) сессиялар.
    """
    profile = getattr(user, "profile", None)
    group = profile.group if profile else None

    for_group = Q(groups__isnull=True)
    if group:
        for_group |= Q(groups=group)
    return ExamSession.objects.filter(for_group, is_active=True).distinct()


def split_duration(duration):
    """
    Уақыт аралығын күн, сағат, минутқа бөледі (шаблонда аударылатын мәтінмен
    көрсету үшін; Django-ның timeuntil сүзгісінде қазақша аударма жоқ).
    """
    minutes_total = int(duration.total_seconds()) // 60
    hours_total, minutes = divmod(minutes_total, 60)
    days, hours = divmod(hours_total, 24)
    return {"days": days, "hours": hours, "minutes": minutes}


def dashboard_sessions(user, now=None):
    """
    Кабинеттегі үш тізім: алдағы, ашық және өткен сессиялар.

    Шекаралар: opens_at <= уақыт < closes_at — ашық, яғни opens_at сәтінде
    сессия ашылады, closes_at сәтінде жабылады. Әр жолда студенттің осы
    сессиядағы әрекеті де беріледі (болмаса — None).
    """
    if now is None:
        now = timezone.now()
    attempts = {attempt.session_id: attempt for attempt in user.attempts.all()}

    upcoming, open_now, past = [], [], []
    for session in visible_sessions(user).order_by("opens_at"):
        row = {"session": session, "attempt": attempts.get(session.pk)}
        if now < session.opens_at:
            row["opens_in"] = split_duration(session.opens_at - now)
            upcoming.append(row)
        elif now < session.closes_at:
            open_now.append(row)
        else:
            past.append(row)

    # Өткен сессиялар — ең соңғысы бірінші
    past.reverse()
    return {"upcoming": upcoming, "open": open_now, "past": past}
