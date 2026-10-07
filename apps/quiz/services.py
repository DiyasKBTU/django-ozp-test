"""
Бизнес-логика (TZ.md, 3–4-бөлімдер): сұрақты сақтау және көшіру, банк толуы,
студентке көрінетін сессиялар, тест нұсқасын құру.
Балл есептеу кейінгі кезеңде осында қосылады.
"""

import logging
import random
from collections import Counter
from datetime import timedelta
from itertools import combinations

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.translation import gettext as _

from .constants import (
    CONTEXTS_PER_TEST,
    LEVEL_QUOTA,
    MIN_CONTEXTS,
    MIN_QUESTIONS_PER_SUBTOPIC,
    QUESTIONS_PER_CONTEXT,
    QUESTIONS_TOTAL,
    SINGLE_QUESTIONS_PER_SUBTOPIC,
    TEST_DURATION_MINUTES,
)
from .models import (
    Answer,
    Attempt,
    AttemptQuestion,
    Context,
    ExamSession,
    Language,
    Level,
    Question,
    Subtopic,
)

logger = logging.getLogger(__name__)


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


def full_contexts(language):
    """Тестке жарайтын контексттер: белсенді және дәл 5 белсенді сұрағы бар."""
    return (
        Context.objects.filter(is_active=True, language=language)
        .annotate(active_count=Count("questions", filter=Q(questions__is_active=True)))
        .filter(active_count=QUESTIONS_PER_CONTEXT)
    )


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

    contexts = []
    for language, label in Language.choices:
        count = full_contexts(language).count()
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


def is_session_open(session, now=None):
    """Сессия қазір ашық па: белсенді және opens_at <= уақыт < closes_at."""
    if now is None:
        now = timezone.now()
    return session.is_active and session.opens_at <= now < session.closes_at


# ---------- Тест нұсқасын құру (TZ.md, 4-бөлім) ----------


class AttemptError(Exception):
    """Тестті бастау мүмкін емес (сессия жабық, бұрын басталған немесе банк толық емес)."""


def bank_error(language):
    """Банкте сұрақ жетпегенде студентке көрсетілетін қате."""
    return AttemptError(
        _(
            "Банкте «%(language)s» тіліндегі сұрақтар жеткіліксіз, тестті бастау "
            "мүмкін емес. Оқытушыға хабарлаңыз."
        )
        % {"language": Language(language).label}
    )


def choose_contexts(language, rng):
    """
    1-қадам: 2 толық контекстті кездейсоқ таңдайды.

    Деңгейлері квотадан (13/30/7) аспайтын жұп бірінші алынады, сонда жеке
    сұрақтармен квотаны дәл толтыруға болады. Қайтарады: контексттер тізімі
    және әр контекстің сұрақтары {контекст id: [(сұрақ id, деңгей), ...]}.
    """
    contexts = list(full_contexts(language))
    if len(contexts) < CONTEXTS_PER_TEST:
        logger.warning("Банкте «%s» тілінде толық контекст жеткіліксіз.", language)
        raise bank_error(language)

    context_questions = {context.pk: [] for context in contexts}
    rows = (
        Question.objects.filter(context__in=contexts, is_active=True)
        .order_by("id")
        .values_list("id", "context_id", "level")
    )
    for question_id, context_id, level in rows:
        context_questions[context_id].append((question_id, level))

    rng.shuffle(contexts)
    pairs = list(combinations(contexts, CONTEXTS_PER_TEST))
    for pair in pairs:
        levels = Counter(
            level for context in pair for _id, level in context_questions[context.pk]
        )
        if all(levels[level] <= LEVEL_QUOTA[level] for level in Level.values):
            return list(pair), context_questions

    logger.warning("«%s» тілінде деңгейі квотаға сыятын контекст жұбы жоқ.", language)
    return list(pairs[0]), context_questions


def find_swap(chosen, pool, remaining):
    """
    Деңгей квотасын түзететін алмастыру іздейді: таңдалған сұрақтың орнына
    сол тақырыпшадағы жетпейтін деңгейдің бос сұрағын қоюға бола ма.

    Алдымен артық деңгейдегі сұрақ алмастырылады. Ондай жол болмаса — квотасы
    дәл толған деңгейдегі сұрақ: сонда жетіспеушілік сол деңгейге ауысады да,
    келесі қадамда басқа тақырыпшада түзетіледі.
    Қайтарады: (тақырыпша id, сұрақтың орны, керек деңгей, ескі деңгей) немесе None.
    """
    needed = [level for level in Level.values if remaining[level] > 0]
    over = [level for level in Level.values if remaining[level] < 0]
    full = [level for level in Level.values if remaining[level] == 0]
    for replaceable in (over, full):
        for need in needed:
            for subtopic_id, items in chosen.items():
                for index, (_id, level) in enumerate(items):
                    if level in replaceable and pool[subtopic_id][need]:
                        return subtopic_id, index, need, level
    return None


def choose_single_questions(language, quota, rng):
    """
    3–4-қадамдар: 20 тақырыпшаның әрқайсысынан 2 жеке сұрақ.

    quota — жеке сұрақтарға қалған деңгей квотасы, мысалы {"A": 11, "B": 24, "C": 5}.
    Әр сұрақ үшін алдымен квотасы бітпеген деңгей таңдалады (қалған квотаға
    қарай кездейсоқ). Ондай сұрақ тақырыпшада жоқ болса — басқа деңгей алынады.
    Соңында квотаны дәлдеу үшін сұрақтар тақырыпша ішінде алмастырылады;
    бәрібір дәл шықпаса (банкте қажет деңгей жетпейді) — журналға ескерту.
    Қайтарады: {тақырыпша id: [(сұрақ id, деңгей), ...]} тақырыпша ретімен.
    """
    # Бос сұрақтар: тақырыпша → деңгей → сұрақ id тізімі (кездейсоқ ретпен)
    pool = {
        subtopic_id: {level: [] for level in Level.values}
        for subtopic_id in Subtopic.objects.order_by("number").values_list("id", flat=True)
    }
    rows = Question.objects.filter(
        language=language, is_active=True, context__isnull=True
    ).values_list("id", "subtopic_id", "level")
    for question_id, subtopic_id, level in rows:
        pool[subtopic_id][level].append(question_id)
    for levels in pool.values():
        for question_ids in levels.values():
            rng.shuffle(question_ids)

    remaining = dict(quota)
    chosen = {subtopic_id: [] for subtopic_id in pool}

    # Тақырыпшаларды кездейсоқ ретпен өтеміз, сонда A/C деңгейлері әр нұсқада
    # әртүрлі тақырыпшаларға түседі
    subtopic_ids = list(pool)
    rng.shuffle(subtopic_ids)
    for subtopic_id in subtopic_ids:
        levels = pool[subtopic_id]
        for _slot in range(SINGLE_QUESTIONS_PER_SUBTOPIC):
            available = [level for level in Level.values if levels[level]]
            if not available:
                logger.warning(
                    "«%s» тілінде тақырыпшада (id=%s) жеке сұрақ жеткіліксіз.",
                    language,
                    subtopic_id,
                )
                raise bank_error(language)
            preferred = [level for level in available if remaining[level] > 0]
            if preferred:
                weights = [remaining[level] for level in preferred]
                level = rng.choices(preferred, weights=weights)[0]
            else:
                level = rng.choice(available)
            chosen[subtopic_id].append((levels[level].pop(), level))
            remaining[level] -= 1

    # Квотаны дәлдеу: сұрақтарды тақырыпша ішінде алмастыру.
    # Қадам саны шектеулі — банк жеткіліксіз болса, шексіз айналмайды.
    for _step in range(QUESTIONS_TOTAL):
        swap = find_swap(chosen, pool, remaining)
        if swap is None:
            break
        subtopic_id, index, need, old_level = swap
        old_id, _level = chosen[subtopic_id][index]
        pool[subtopic_id][old_level].append(old_id)
        chosen[subtopic_id][index] = (pool[subtopic_id][need].pop(), need)
        remaining[need] -= 1
        remaining[old_level] += 1

    if any(remaining.values()):
        logger.warning(
            "«%s» тіліндегі нұсқа деңгей квотасына дәл сәйкес емес "
            "(жетпейтіні оң, артығы теріс: %s): банкте қажет деңгейдегі сұрақ жоқ.",
            language,
            remaining,
        )
    return chosen


def build_variant(language, rng=None):
    """
    Нұсқа құру алгоритмі (TZ.md, 4-бөлім), тек берілген тілдегі белсенді сұрақтардан.

    Қайтарады: 50 сұрақтың id тізімі тест ретімен — 1–40 жеке сұрақтар
    тақырыпша ретімен (01–20), 41–50 екі контекстің сұрақтары.
    rng — кездейсоқ сандар генераторы (тесттерде қайталанатын нәтиже үшін).
    """
    if rng is None:
        rng = random.Random()

    # 1-қадам: 2 контекст және олардың 10 сұрағы
    contexts, context_questions = choose_contexts(language, rng)

    # 2-қадам: контекст сұрақтарының деңгейін санап, қалған квотаны есептеу
    context_levels = Counter(
        level for context in contexts for _id, level in context_questions[context.pk]
    )
    quota = {level: LEVEL_QUOTA[level] - context_levels[level] for level in Level.values}

    # 3–4-қадамдар: әр тақырыпшадан 2 жеке сұрақ
    chosen = choose_single_questions(language, quota, rng)

    # 5-қадам: жеке сұрақтар тақырыпша ретімен, соңында контексттер
    question_ids = [question_id for items in chosen.values() for question_id, _level in items]
    for context in contexts:
        question_ids += [question_id for question_id, _level in context_questions[context.pk]]

    if len(question_ids) != QUESTIONS_TOTAL:
        logger.warning("«%s» тіліндегі нұсқада %s сұрақ шықты.", language, len(question_ids))
        raise bank_error(language)
    return question_ids


@transaction.atomic
def create_attempt(user, session, language, now=None, rng=None):
    """
    Тестті бастау: сессия ашық екенін және студент бұл сессияда бұрын
    бастамағанын тексереді, нұсқа құрып, әр сұрақтың жауап нұсқаларын араластырады.
    deadline = min(басталған уақыт + 125 минут, сессияның жабылуы).
    """
    if now is None:
        now = timezone.now()
    if rng is None:
        rng = random.Random()

    if not is_session_open(session, now):
        raise AttemptError(_("Бұл сессия қазір ашық емес."))
    if Attempt.objects.filter(user=user, session=session).exists():
        raise AttemptError(_("Сіз бұл сессияда тестті бұрын бастағансыз."))

    question_ids = build_variant(language, rng)

    attempt = Attempt.objects.create(
        user=user,
        session=session,
        language=language,
        started_at=now,
        deadline=min(now + timedelta(minutes=TEST_DURATION_MINUTES), session.closes_at),
    )

    # Әр сұрақтың жауап нұсқалары: {сұрақ id: [жауап id, ...]}
    answers = {question_id: [] for question_id in question_ids}
    rows = Answer.objects.filter(question_id__in=question_ids).values_list(
        "question_id", "id"
    )
    for question_id, answer_id in rows:
        answers[question_id].append(answer_id)

    items = []
    for order, question_id in enumerate(question_ids, start=1):
        answer_order = sorted(answers[question_id])
        rng.shuffle(answer_order)
        items.append(
            AttemptQuestion(
                attempt=attempt,
                question_id=question_id,
                order=order,
                answer_order=answer_order,
            )
        )
    AttemptQuestion.objects.bulk_create(items)
    return attempt
