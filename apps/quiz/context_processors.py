from .services import active_attempt


def attempt_in_progress(request):
    """
    Барлық шаблонға: студенттің жүріп жатқан тесті (болмаса — None).
    Навигацияда «Шығу» орнына «Тестке оралу» көрсету үшін (base.html).
    """
    return {"active_attempt": active_attempt(request.user)}
