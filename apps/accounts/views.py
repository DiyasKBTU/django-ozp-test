from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import RegisterForm


def register(request):
    """Тіркелу: сәтті болса, қолданушы бірден кіріп, кабинетке өтеді."""
    if request.user.is_authenticated:
        return redirect("accounts:after_login")

    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("quiz:dashboard")
    else:
        form = RegisterForm()
    return render(request, "accounts/register.html", {"form": form})


@login_required
def after_login(request):
    """Кіргеннен кейін: оқытушы — сұрақтар бетіне, студент — кабинетке."""
    if request.user.is_staff:
        return redirect("quiz:teacher_questions")
    return redirect("quiz:dashboard")
