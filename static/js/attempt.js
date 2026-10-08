// Тест беті (templates/quiz/question.html): жауапты бетті қайта жүктемей сақтау.
// Сұрақтар арасында ауысу, кезек пен AJAX — question_pages.js.
// Жауапты өзгертуге болады (тест аяқталғанша); мерзімді бәрібір сервер тексереді:
// уақыт өтсе, сервер нәтиже бетіне жібереді.
(function () {
    var pages = window.QuestionPages;
    if (!pages) {
        return;
    }

    // Экрандағы таңдауды көрсетеді (answerId === "" — ештеңе таңдалмаған)
    function markSelected(form, answerId) {
        form.querySelectorAll("label").forEach(function (label) {
            var input = label.querySelector("input");
            var selected = answerId !== "" && input.value === answerId;
            input.checked = selected;
            label.classList.toggle("active", selected);
        });
    }

    function setSaved(number, saved) {
        pages.block(number).querySelector(".answer-saved").classList.toggle("d-none", !saved);
    }

    // Сақтау сәтсіз: экрандағы таңдауды серверде сақталғанына қайтарамыз
    function restore(form, number, error) {
        markSelected(form, form.dataset.saved);
        setSaved(number, form.dataset.saved !== "");
        pages.showError(number, error);
    }

    pages.onAnswer(function (form, data) {
        var number = Number(form.dataset.number);
        markSelected(form, data.get("answer") || "");
        return pages
            .send(form, data)
            .then(function (reply) {
                if (!reply) {
                    return;
                }
                if (!reply.ok) {
                    restore(form, number, reply.result.error);
                    return;
                }
                form.dataset.saved = data.get("answer");
                pages.navLink(number).classList.remove("btn-outline-secondary");
                pages.navLink(number).classList.add("btn-primary");
                document.getElementById("unanswered-count").textContent = reply.result.unanswered;
                setSaved(number, true);
                pages.showError(number, "");
            })
            .catch(function () {
                restore(form, number, pages.networkError);
            });
    });
})();
