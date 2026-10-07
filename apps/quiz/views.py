from django.shortcuts import render

from .constants import QUESTIONS_TOTAL, TEST_DURATION_MINUTES


def home(request):
    """Басты бет: тест туралы қысқаша мәлімет."""
    context = {
        "questions_total": QUESTIONS_TOTAL,
        "duration_minutes": TEST_DURATION_MINUTES,
    }
    return render(request, "quiz/home.html", context)
