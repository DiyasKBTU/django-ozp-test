from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import get_language
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache

from .constants import PRACTICE_QUESTIONS, QUESTIONS_TOTAL
from .forms import AttemptAnswerForm, PracticeStartForm, StartAttemptForm
from .models import Attempt, Language
from .services import (
    AttemptError,
    attempt_result,
    can_see_answers,
    create_attempt,
    dashboard_sessions,
    default_subject,
    finish_attempt,
    finish_expired_attempts,
    finish_if_expired,
    first_unanswered_number,
    is_session_open,
    practice_answer,
    practice_question_data,
    practice_summary,
    question_page_data,
    remaining_seconds,
    save_answer,
    start_practice,
    unanswered_numbers,
    visible_sessions,
)


def home(request):
    """Басты бет: тест туралы қысқаша мәлімет."""
    subject = default_subject()
    context = {
        "questions_total": QUESTIONS_TOTAL,
        "duration_minutes": subject.duration_minutes if subject else None,
    }
    return render(request, "quiz/home.html", context)


@login_required
def dashboard(request):
    """Жеке кабинет: алдағы, ашық және өткен сессиялар, әрекеттер тарихы."""
    # Мерзімі өтіп кеткен тесттер «Аяқталды» болып, балымен көрінсін
    finish_expired_attempts(request.user.attempts.all())
    context = dashboard_sessions(request.user)
    context["attempts"] = request.user.attempts.select_related("session")
    context["questions_total"] = QUESTIONS_TOTAL
    return render(request, "quiz/dashboard.html", context)


# ---------- Тест тапсыру ----------


def interface_language():
    """Тест/жаттығу тілінің әдепкі мәні — интерфейс тілі (kk немесе ru)."""
    return Language.RU if get_language() == "ru" else Language.KK


def get_own_attempt(request, attempt_id):
    """Студенттің өз әрекеті (бөтен әрекет — 404); мерзімі өтсе, аяқталады."""
    attempt = get_object_or_404(
        Attempt.objects.select_related("session"), pk=attempt_id, user=request.user
    )
    return finish_if_expired(attempt)


def redirect_to_attempt(attempt):
    """Аяқталған әрекет — нәтиже бетіне, аяқталмағаны — жауап берілмеген сұраққа."""
    if attempt.status == Attempt.Status.FINISHED:
        return redirect("quiz:attempt_result", attempt.pk)
    return redirect("quiz:attempt_question", attempt.pk, first_unanswered_number(attempt))


@login_required
def session_start(request, session_id):
    """
    Тестті бастау: GET — ережелер және тест тілін таңдау,
    POST — нұсқа құрып, 1-сұраққа өту.
    Студент бұл сессияда бұрын бастаса, жаңа әрекет жасалмайды — сол әрекетке қайтады.
    """
    # Бөтен топтың сессиясы — 404
    session = get_object_or_404(
        visible_sessions(request.user).select_related("subject"), pk=session_id
    )

    attempt = Attempt.objects.filter(user=request.user, session=session).first()
    if attempt:
        return redirect_to_attempt(finish_if_expired(attempt))

    form = StartAttemptForm(request.POST or None, initial={"language": interface_language()})
    if request.method == "POST" and form.is_valid():
        try:
            attempt = create_attempt(request.user, session, form.cleaned_data["language"])
        except AttemptError as error:
            messages.error(request, str(error))
            return redirect("quiz:session_start", session.pk)
        return redirect("quiz:attempt_question", attempt.pk, 1)

    context = {
        "session": session,
        "is_open": is_session_open(session),
        "form": form,
        "questions_total": QUESTIONS_TOTAL,
        "duration_minutes": session.subject.duration_minutes,
    }
    return render(request, "quiz/session_start.html", context)


@never_cache
@login_required
def attempt_question(request, attempt_id, number):
    """n-сұрақ беті: GET — көрсету, POST — жауапты сақтау (сол бетке қайтады)."""
    attempt = get_own_attempt(request, attempt_id)
    if attempt.status == Attempt.Status.FINISHED:
        return redirect("quiz:attempt_result", attempt.pk)
    item = get_object_or_404(
        attempt.items.select_related("question__context"), order=number
    )

    if request.method == "POST":
        form = AttemptAnswerForm(item.answer_order, request.POST)
        if not form.is_valid():
            messages.error(request, _("Жауап нұсқасын таңдаңыз."))
        elif not save_answer(item, form.cleaned_data["answer"]):
            # Мерзім осы сәтте өтті: жауап қабылданбайды, тест аяқталады
            finish_attempt(attempt)
            messages.warning(request, _("Тест уақыты бітті, жауап қабылданбады."))
            return redirect("quiz:attempt_result", attempt.pk)
        return redirect("quiz:attempt_question", attempt.pk, number)

    context = question_page_data(attempt, item)
    context.update({"attempt": attempt, "item": item, "question": item.question})
    return render(request, "quiz/question.html", context)


@never_cache
@login_required
def attempt_finish(request, attempt_id):
    """Тестті аяқтау: GET — растау (жауап берілмеген сұрақтар), POST — аяқтау."""
    attempt = get_own_attempt(request, attempt_id)
    if attempt.status == Attempt.Status.FINISHED:
        return redirect("quiz:attempt_result", attempt.pk)

    if request.method == "POST":
        finish_attempt(attempt)
        return redirect("quiz:attempt_result", attempt.pk)

    context = {
        "attempt": attempt,
        "unanswered": unanswered_numbers(attempt),
        "remaining_seconds": remaining_seconds(attempt),
    }
    return render(request, "quiz/finish.html", context)


@never_cache
@login_required
def attempt_result_page(request, attempt_id):
    """
    Нәтиже беті: балл, деңгей және тақырып бойынша талдау, дұрыс жауаптар.
    Студент тек өз нәтижесін көреді (бөтені — 404), оқытушы — барлығын.
    """
    attempts = Attempt.objects.select_related("session", "user")
    if not request.user.is_staff:
        attempts = attempts.filter(user=request.user)
    attempt = finish_if_expired(get_object_or_404(attempts, pk=attempt_id))

    if attempt.status != Attempt.Status.FINISHED:
        if attempt.user_id == request.user.pk:
            return redirect_to_attempt(attempt)
        # Оқытушы: тест әлі жүріп жатыр, нәтиже жоқ
        return render(request, "quiz/result.html", {"attempt": attempt})

    show_answers = can_see_answers(attempt, request.user)
    context = {
        "attempt": attempt,
        "result": attempt_result(attempt, with_answers=show_answers),
        "show_answers": show_answers,
    }
    return render(request, "quiz/result.html", context)


# ---------- Тақырыптық жаттығу (таймерсіз, дұрыс жауап бірден көрсетіледі) ----------

# Жаттығу күйі студенттің Django сессиясында осы кілтпен сақталады
PRACTICE_SESSION_KEY = "practice"


@login_required
def practice_start(request):
    """GET — тақырып пен тілді таңдау, POST — жаңа жаттығу (алдыңғысының орнына)."""
    form = PracticeStartForm(request.POST or None, initial={"language": interface_language()})
    if request.method == "POST" and form.is_valid():
        try:
            practice = start_practice(
                form.cleaned_data["topic"], form.cleaned_data["language"]
            )
        except AttemptError as error:
            messages.error(request, str(error))
            return redirect("quiz:practice_start")
        request.session[PRACTICE_SESSION_KEY] = practice
        return redirect("quiz:practice_question", 1)

    context = {
        "form": form,
        "has_practice": PRACTICE_SESSION_KEY in request.session,
        "practice_questions": PRACTICE_QUESTIONS,
    }
    return render(request, "quiz/practice_start.html", context)


@login_required
def practice_question(request, number):
    """Жаттығудың n-сұрағы: POST — жауап (бір рет), содан кейін дұрыс жауап көрсетіледі."""
    practice = request.session.get(PRACTICE_SESSION_KEY)
    if not practice:
        return redirect("quiz:practice_start")
    if not 1 <= number <= len(practice["items"]):
        raise Http404

    if request.method == "POST":
        item = practice["items"][number - 1]
        form = AttemptAnswerForm(item["answer_order"], request.POST)
        if form.is_valid():
            practice_answer(practice, number, form.cleaned_data["answer"])
            # Сессиядағы ішкі сөздік өзгерді — Django-ға сақтау керектігін айтамыз
            request.session.modified = True
        else:
            messages.error(request, _("Жауап нұсқасын таңдаңыз."))
        return redirect("quiz:practice_question", number)

    context = practice_question_data(practice, number)
    if context is None:
        del request.session[PRACTICE_SESSION_KEY]
        messages.warning(request, _("Сұрақ банктен өшірілген. Жаттығуды қайта бастаңыз."))
        return redirect("quiz:practice_start")
    return render(request, "quiz/practice_question.html", context)


@login_required
def practice_result(request):
    """Жаттығу қорытындысы: дұрыс жауаптар саны және әр сұраққа сілтеме."""
    practice = request.session.get(PRACTICE_SESSION_KEY)
    if not practice:
        return redirect("quiz:practice_start")
    return render(request, "quiz/practice_result.html", {"summary": practice_summary(practice)})
