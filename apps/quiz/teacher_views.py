"""
Оқытушы беттері (/teacher/...): сұрақтар, контексттер, банк толуы, нәтижелер.
Барлығы тек оқытушыға (is_staff) ашық.
"""

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .constants import QUESTIONS_PER_CONTEXT, QUESTIONS_TOTAL
from .forms import (
    AnswerFormSet,
    ContextForm,
    QuestionFilterForm,
    QuestionForm,
    ResultFilterForm,
    SampleVariantForm,
    initial_from_query,
)
from .models import Attempt, Context, Language, Question
from .services import (
    AttemptError,
    bank_coverage,
    build_variant,
    copy_question,
    finish_expired_attempts,
    results_rows,
    results_summary,
    save_question,
    toggle_question_active,
    variant_summary,
    write_results_csv,
)

# Сұрақтар тізімінің бір бетіндегі жол саны
QUESTIONS_PER_PAGE = 50


def redirect_back(request, default):
    """Формадағы `next` мекенжайына (тек осы сайт ішінде) немесе default-қа қайтарады."""
    next_url = request.POST.get("next", "")
    if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return redirect(next_url)
    return redirect(default)


# ---------- Сұрақтар ----------


@staff_member_required
def question_list(request):
    filter_form = QuestionFilterForm(request.GET)
    questions = filter_form.filter(
        Question.objects.select_related("subtopic__topic", "context")
    )
    page = Paginator(questions, QUESTIONS_PER_PAGE).get_page(request.GET.get("page"))

    # Бет ауыстырғанда сүзгі сақталуы үшін
    query = request.GET.copy()
    query.pop("page", None)

    return render(
        request,
        "teacher/question_list.html",
        {"filter_form": filter_form, "page": page, "query": query.urlencode()},
    )


def question_form_page(request, question=None):
    """Сұрақ енгізу (question=None) және өңдеу беттерінің ортақ бөлігі."""
    if request.method == "POST":
        form = QuestionForm(request.POST, request.FILES, instance=question)
        formset = AnswerFormSet(request.POST, instance=form.instance)
        if form.is_valid() and formset.is_valid():
            question = save_question(form, formset)
            if "save_and_next" in request.POST:
                messages.success(request, _("Сұрақ сақталды. Келесісін енгізіңіз."))
                new_url = reverse("quiz:teacher_question_create")
                return redirect(f"{new_url}?{form.next_question_query()}")
            messages.success(request, _("Сұрақ сақталды."))
            return redirect("quiz:teacher_question_edit", pk=question.pk)
    else:
        initial = initial_from_query(request.GET) if question is None else None
        form = QuestionForm(instance=question, initial=initial)
        formset = AnswerFormSet(instance=form.instance)

    # Алдын ала қарау — сақталған нұсқасы (форма өзгерткен объект емес)
    preview = None
    if question is not None:
        preview = Question.objects.select_related("context").get(pk=question.pk)

    return render(
        request,
        "teacher/question_form.html",
        {"form": form, "formset": formset, "question": question, "preview": preview},
    )


@staff_member_required
def question_create(request):
    return question_form_page(request)


@staff_member_required
def question_edit(request, pk):
    question = get_object_or_404(Question, pk=pk)
    return question_form_page(request, question)


@staff_member_required
@require_POST
def question_copy(request, pk):
    question = get_object_or_404(Question, pk=pk)
    copy = copy_question(question)
    messages.success(request, _("Көшірмесі жасалды, қажет болса өңдеңіз."))
    return redirect("quiz:teacher_question_edit", pk=copy.pk)


@staff_member_required
@require_POST
def question_toggle(request, pk):
    question = get_object_or_404(Question, pk=pk)
    if not toggle_question_active(question):
        messages.error(
            request,
            _("Контекстте %(count)s белсенді сұрақ бар, бұл сұрақты белсендіруге болмайды.")
            % {"count": QUESTIONS_PER_CONTEXT},
        )
    return redirect_back(request, "quiz:teacher_questions")


# ---------- Контексттер ----------


@staff_member_required
def context_list(request):
    contexts = Context.objects.annotate(
        active_count=Count("questions", filter=Q(questions__is_active=True))
    )
    return render(
        request,
        "teacher/context_list.html",
        {"contexts": contexts, "questions_per_context": QUESTIONS_PER_CONTEXT},
    )


def context_form_page(request, quiz_context=None):
    """Контекст жасау (quiz_context=None) және өңдеу беттерінің ортақ бөлігі."""
    if request.method == "POST":
        form = ContextForm(request.POST, request.FILES, instance=quiz_context)
        if form.is_valid():
            quiz_context = form.save()
            messages.success(request, _("Контекст сақталды."))
            return redirect("quiz:teacher_context_edit", pk=quiz_context.pk)
    else:
        form = ContextForm(instance=quiz_context)

    questions = []
    active_count = 0
    if quiz_context is not None:
        questions = quiz_context.questions.select_related("subtopic")
        active_count = quiz_context.active_questions_count()

    return render(
        request,
        "teacher/context_form.html",
        {
            "form": form,
            "quiz_context": quiz_context,
            "questions": questions,
            "active_count": active_count,
            "questions_per_context": QUESTIONS_PER_CONTEXT,
        },
    )


@staff_member_required
def context_create(request):
    return context_form_page(request)


@staff_member_required
def context_edit(request, pk):
    quiz_context = get_object_or_404(Context, pk=pk)
    return context_form_page(request, quiz_context)


# ---------- Банк толуы ----------


@staff_member_required
def bank(request):
    return render(request, "teacher/bank.html", {"coverage": bank_coverage()})


@staff_member_required
@never_cache
def bank_sample(request):
    """
    Үлгі нұсқа: build_variant() банктен нұсқа құрады, бірақ дерекқорға ештеңе
    жазылмайды (Attempt жасалмайды). Бет жаңартылған сайын жаңа нұсқа шығады.
    """
    language = SampleVariantForm(request.GET).get_language()
    context = {"language": language, "languages": Language.choices}
    try:
        context["summary"] = variant_summary(build_variant(language))
    except AttemptError as error:
        context["error"] = str(error)
    return render(request, "teacher/bank_sample.html", context)


# ---------- Нәтижелер ----------

# Нәтижелер кестесінің бір бетіндегі жол саны
RESULTS_PER_PAGE = 50


def filtered_attempts(request):
    """
    Сүзгіден өткен әрекеттер (нәтижелер беті мен CSV үшін ортақ).
    Алдымен мерзімі өткен әрекеттер аяқталады — балы дұрыс көрінсін.
    """
    finish_expired_attempts()
    filter_form = ResultFilterForm(request.GET)
    attempts = filter_form.filter(
        Attempt.objects.select_related("user__profile__group", "session").order_by(
            "-session__opens_at", "user__last_name", "user__first_name", "user__username"
        )
    )
    return filter_form, attempts


@staff_member_required
def results(request):
    filter_form, attempts = filtered_attempts(request)
    page = Paginator(attempts, RESULTS_PER_PAGE).get_page(request.GET.get("page"))

    # Бет ауыстырғанда және CSV жүктегенде сүзгі сақталуы үшін
    query = request.GET.copy()
    query.pop("page", None)

    context = {
        "filter_form": filter_form,
        "page": page,
        "rows": results_rows(page),
        "summary": results_summary(list(attempts)),
        "query": query.urlencode(),
        "questions_total": QUESTIONS_TOTAL,
    }
    return render(request, "teacher/results.html", context)


@staff_member_required
def results_export(request):
    """Сүзгіден өткен нәтижелерді CSV файл етіп береді."""
    _filter_form, attempts = filtered_attempts(request)
    filename = f"results-{timezone.localdate():%Y-%m-%d}.csv"
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    write_results_csv(attempts, response)
    return response
