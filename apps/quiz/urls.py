from django.urls import path

from . import teacher_views, views

app_name = "quiz"

urlpatterns = [
    path("", views.home, name="home"),
    # ---------- Студент беттері ----------
    path("dashboard/", views.dashboard, name="dashboard"),
    path("session/<int:session_id>/start/", views.session_start, name="session_start"),
    path(
        "test/<int:attempt_id>/q/<int:number>/",
        views.attempt_question,
        name="attempt_question",
    ),
    path("test/<int:attempt_id>/finish/", views.attempt_finish, name="attempt_finish"),
    path(
        "test/<int:attempt_id>/result/",
        views.attempt_result_page,
        name="attempt_result",
    ),
    # ---------- Оқытушы беттері ----------
    path("teacher/questions/", teacher_views.question_list, name="teacher_questions"),
    path(
        "teacher/questions/new/",
        teacher_views.question_create,
        name="teacher_question_create",
    ),
    path(
        "teacher/questions/<int:pk>/edit/",
        teacher_views.question_edit,
        name="teacher_question_edit",
    ),
    path(
        "teacher/questions/<int:pk>/copy/",
        teacher_views.question_copy,
        name="teacher_question_copy",
    ),
    path(
        "teacher/questions/<int:pk>/toggle/",
        teacher_views.question_toggle,
        name="teacher_question_toggle",
    ),
    path("teacher/contexts/", teacher_views.context_list, name="teacher_contexts"),
    path(
        "teacher/contexts/new/",
        teacher_views.context_create,
        name="teacher_context_create",
    ),
    path(
        "teacher/contexts/<int:pk>/edit/",
        teacher_views.context_edit,
        name="teacher_context_edit",
    ),
    path("teacher/bank/", teacher_views.bank, name="teacher_bank"),
    path("teacher/bank/sample/", teacher_views.bank_sample, name="teacher_bank_sample"),
    path("teacher/results/", teacher_views.results, name="teacher_results"),
    path(
        "teacher/results/export/",
        teacher_views.results_export,
        name="teacher_results_export",
    ),
]
