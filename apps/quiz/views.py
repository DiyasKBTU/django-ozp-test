from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from .constants import QUESTIONS_TOTAL, TEST_DURATION_MINUTES
from .services import dashboard_sessions, is_session_open, visible_sessions


def home(request):
    """Басты бет: тест туралы қысқаша мәлімет."""
    context = {
        "questions_total": QUESTIONS_TOTAL,
        "duration_minutes": TEST_DURATION_MINUTES,
    }
    return render(request, "quiz/home.html", context)


@login_required
def dashboard(request):
    """Жеке кабинет: алдағы, ашық және өткен сессиялар, әрекеттер тарихы."""
    context = dashboard_sessions(request.user)
    context["attempts"] = request.user.attempts.select_related("session")
    context["questions_total"] = QUESTIONS_TOTAL
    return render(request, "quiz/dashboard.html", context)


@login_required
def session_start(request, session_id):
    """
    Тестті бастау беті. Әзірге тек сессияны көрсетеді;
    тіл таңдау мен нұсқа құру 5-кезеңде қосылады.
    """
    # Бөтен топтың сессиясы — 404
    session = get_object_or_404(visible_sessions(request.user), pk=session_id)
    context = {"session": session, "is_open": is_session_open(session)}
    return render(request, "quiz/session_start.html", context)
