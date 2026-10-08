from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import get_language
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache

from .constants import PRACTICE_QUESTIONS, QUESTIONS_TOTAL
from .forms import AttemptAnswerForm, PracticeStartForm
from .models import Attempt, Language
from .services import (
    AttemptError,
    attempt_page_data,
    attempt_result,
    can_see_answers,
    create_attempt,
    active_subjects,
    dashboard_sessions,
    finish_attempt,
    finish_expired_attempts,
    finish_if_expired,
    first_unanswered_number,
    is_session_open,
    practice_answer,
    practice_answer_feedback,
    practice_page_data,
    practice_summary,
    remaining_seconds,
    save_answer,
    start_practice,
    student_language,
    student_subject,
    teacher_subjects,
    unanswered_numbers,
    visible_sessions,
)


def home(request):
    """Басты бет: тест туралы қысқаша мәлімет және пәндер (тест уақытымен)."""
    context = {"questions_total": QUESTIONS_TOTAL, "subjects": active_subjects()}
    return render(request, "quiz/home.html", context)


@login_required
def dashboard(request):
    """Жеке кабинет: алдағы, ашық және өткен сессиялар, әрекеттер тарихы."""
    # Мерзімі өтіп кеткен тесттер «Аяқталды» болып, балымен көрінсін
    finish_expired_attempts(request.user.attempts.all())
    context = dashboard_sessions(request.user)
    context["attempts"] = request.user.attempts.select_related("session")
    context["questions_total"] = QUESTIONS_TOTAL
    context["subject"] = student_subject(request.user)
    return render(request, "quiz/dashboard.html", context)


# ---------- Тест тапсыру ----------


def interface_language():
    """Интерфейс тілі (kk немесе ru) — топтың тілі белгісіз болғанда жаттығу тілінің әдепкісі."""
    return Language.RU if get_language() == "ru" else Language.KK


def get_own_attempt(request, attempt_id):
    """Студенттің өз әрекеті (бөтен әрекет — 404); мерзімі өтсе, аяқталады."""
    attempt = get_object_or_404(
        Attempt.objects.select_related("session__subject"), pk=attempt_id, user=request.user
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
    Тестті бастау: GET — ережелер, POST — нұсқа құрып, 1-сұраққа өту.
    Тест тілін студент таңдамайды — ол тобының оқыту тілі (StudyGroup.language).
    Студент бұл сессияда бұрын бастаса, жаңа әрекет жасалмайды — сол әрекетке қайтады.
    """
    # Бөтен топтың сессиясы — 404
    session = get_object_or_404(
        visible_sessions(request.user).select_related("subject"), pk=session_id
    )

    attempt = Attempt.objects.filter(user=request.user, session=session).first()
    if attempt:
        return redirect_to_attempt(finish_if_expired(attempt))

    # Сессияны тек тобы бар студент көреді, сондықтан тіл әрқашан белгілі
    language = student_language(request.user)
    if request.method == "POST":
        try:
            attempt = create_attempt(request.user, session, language)
        except AttemptError as error:
            messages.error(request, str(error))
            return redirect("quiz:session_start", session.pk)
        return redirect("quiz:attempt_question", attempt.pk, 1)

    context = {
        "session": session,
        "is_open": is_session_open(session),
        "language_label": Language(language).label,
        "questions_total": QUESTIONS_TOTAL,
        "duration_minutes": session.subject.duration_minutes,
    }
    return render(request, "quiz/session_start.html", context)


def is_ajax(request):
    """Сұранысты static/js/attempt.js жіберді ме (жауап JSON болады)."""
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


@never_cache
@login_required
def attempt_question(request, attempt_id, number):
    """
    Тест беті: GET — барлық сұрақ (n-сұрақ көрінеді), POST — n-сұрақтың жауабын сақтау.
    attempt.js жауапты AJAX арқылы жібереді — оған JSON қайтарылады, бет қайта
    жүктелмейді. JS жоқ болса — бұрынғыдай форма жіберіліп, сол бетке қайтады.
    """
    attempt = get_own_attempt(request, attempt_id)
    result_url = reverse("quiz:attempt_result", args=[attempt.pk])
    if attempt.status == Attempt.Status.FINISHED:
        if is_ajax(request):
            return JsonResponse({"redirect": result_url})
        return redirect(result_url)
    item = get_object_or_404(attempt.items, order=number)

    if request.method == "POST":
        form = AttemptAnswerForm(item.answer_order, request.POST)
        if not form.is_valid():
            error = _("Жауап нұсқасын таңдаңыз.")
            if is_ajax(request):
                return JsonResponse({"error": error}, status=400)
            messages.error(request, error)
        elif not save_answer(item, form.cleaned_data["answer"]):
            # Мерзім осы сәтте өтті: жауап қабылданбайды, тест аяқталады
            finish_attempt(attempt)
            messages.warning(request, _("Тест уақыты бітті, жауап қабылданбады."))
            if is_ajax(request):
                return JsonResponse({"redirect": result_url})
            return redirect(result_url)
        elif is_ajax(request):
            return JsonResponse({"saved": True, "unanswered": len(unanswered_numbers(attempt))})
        return redirect("quiz:attempt_question", attempt.pk, number)

    context = attempt_page_data(attempt)
    context.update(
        {
            "attempt": attempt,
            "number": number,
            # Формулалар (KaTeX) тек формуласы бар пәнде қосылады
            "uses_formulas": attempt.session.subject.uses_formulas,
        }
    )
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
    Студент тек өз нәтижесін көреді (бөтені — 404), оқытушы — өз пәндерінің
    нәтижелерін (басқа пәннікі — 404).
    """
    attempts = Attempt.objects.select_related("session__subject", "user")
    if request.user.is_staff:
        attempts = attempts.filter(session__subject__in=teacher_subjects(request.user))
    else:
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
        "uses_formulas": attempt.session.subject.uses_formulas,
    }
    return render(request, "quiz/result.html", context)


# ---------- Тақырыптық жаттығу (таймерсіз, дұрыс жауап бірден көрсетіледі) ----------

# Жаттығу күйі студенттің Django сессиясында осы кілтпен сақталады
PRACTICE_SESSION_KEY = "practice"


@login_required
def practice_start(request):
    """
    GET — тақырып пен тілді таңдау, POST — жаңа жаттығу (алдыңғысының орнына).
    Тақырыптар — тек студенттің пәнінен (тобы жоқ болса — тізім бос).
    """
    subject = student_subject(request.user)
    # Әдепкі тіл — топтың тілі; жаттығу бағаланбайды, сондықтан тілді өзгертуге болады
    language = student_language(request.user) or interface_language()
    form = PracticeStartForm(
        request.POST or None, initial={"language": language}, subject=subject
    )
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
        "subject": subject,
        "has_practice": PRACTICE_SESSION_KEY in request.session,
        "practice_questions": PRACTICE_QUESTIONS,
    }
    return render(request, "quiz/practice_start.html", context)


def restart_practice(request):
    """Жаттығудың сұрағы банктен өшірілген: жаттығу жойылып, бастау бетіне."""
    del request.session[PRACTICE_SESSION_KEY]
    messages.warning(request, _("Сұрақ банктен өшірілген. Жаттығуды қайта бастаңыз."))
    start_url = reverse("quiz:practice_start")
    if is_ajax(request):
        return JsonResponse({"redirect": start_url})
    return redirect(start_url)


@login_required
def practice_question(request, number):
    """
    Жаттығу беті: GET — барлық сұрақ (n-сұрақ көрінеді), POST — n-сұрақтың жауабы
    (бір рет), содан кейін дұрыс жауап көрсетіледі. practice.js жауапты AJAX арқылы
    жібереді — оған JSON (таңдалған және дұрыс жауап) қайтарылады, бет қайта жүктелмейді.
    """
    practice = request.session.get(PRACTICE_SESSION_KEY)
    if not practice:
        if is_ajax(request):
            return JsonResponse({"redirect": reverse("quiz:practice_start")})
        return redirect("quiz:practice_start")
    if not 1 <= number <= len(practice["items"]):
        raise Http404

    if request.method == "POST":
        item = practice["items"][number - 1]
        form = AttemptAnswerForm(item["answer_order"], request.POST)
        if not form.is_valid():
            error = _("Жауап нұсқасын таңдаңыз.")
            if is_ajax(request):
                return JsonResponse({"error": error}, status=400)
            messages.error(request, error)
            return redirect("quiz:practice_question", number)
        practice_answer(practice, number, form.cleaned_data["answer"])
        # Сессиядағы ішкі сөздік өзгерді — Django-ға сақтау керектігін айтамыз
        request.session.modified = True
        if is_ajax(request):
            feedback = practice_answer_feedback(practice, number)
            if feedback is None:
                return restart_practice(request)
            return JsonResponse(feedback)
        return redirect("quiz:practice_question", number)

    context = practice_page_data(practice)
    if context is None:
        return restart_practice(request)
    context["number"] = number
    return render(request, "quiz/practice_question.html", context)


@login_required
def practice_result(request):
    """Жаттығу қорытындысы: дұрыс жауаптар саны және әр сұраққа сілтеме."""
    practice = request.session.get(PRACTICE_SESSION_KEY)
    if not practice:
        return redirect("quiz:practice_start")
    return render(request, "quiz/practice_result.html", {"summary": practice_summary(practice)})
