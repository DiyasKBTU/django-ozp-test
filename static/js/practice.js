// Жаттығу беті (templates/quiz/practice_question.html): жауапты бетті қайта жүктемей беру.
// Сұрақтар арасында ауысу, кезек пен AJAX — question_pages.js.
// Жауап бір рет беріледі. Дұрыс жауапты сервер тек жауап берілген соң айтады
// (JSON: selected_id, correct_id, is_correct) — содан кейін дұрысы жасыл, қате таңдау қызыл.
(function () {
    var pages = window.QuestionPages;
    if (!pages) {
        return;
    }

    function setDisabled(form, disabled) {
        form.querySelectorAll("input[type=radio]").forEach(function (input) {
            input.disabled = disabled;
        });
    }

    function showFeedback(form, number, feedback) {
        form.querySelectorAll("label[data-answer]").forEach(function (label) {
            var id = Number(label.dataset.answer);
            var isCorrect = id === feedback.correct_id;
            var isSelected = id === feedback.selected_id;
            label.querySelector("input").checked = isSelected;
            label.classList.remove("list-group-item-action");
            label.classList.toggle("list-group-item-success", isCorrect);
            label.classList.toggle("list-group-item-danger", isSelected && !isCorrect);
            label.querySelector(".badge-correct").classList.toggle("d-none", !isCorrect);
            label.querySelector(".badge-selected").classList.toggle("d-none", !isSelected);
        });
        setDisabled(form, true);

        var section = pages.block(number);
        section.querySelector(".feedback-correct").classList.toggle("d-none", !feedback.is_correct);
        section.querySelector(".feedback-wrong").classList.toggle("d-none", feedback.is_correct);
        // Келесі қадамды ерекшелейміз: «Келесі» немесе (соңғы сұрақта) «Қорытынды»
        var next = section.querySelector(".next-link");
        if (next) {
            next.classList.replace("btn-outline-primary", "btn-primary");
        } else {
            section.querySelector(".finish-link").classList.replace("btn-outline-success", "btn-success");
        }

        var cell = pages.navLink(number);
        cell.classList.remove("btn-outline-secondary");
        cell.classList.add(feedback.is_correct ? "btn-success" : "btn-danger");
        pages.showError(number, "");
    }

    pages.onAnswer(function (form, data) {
        var number = Number(form.dataset.number);
        // Жауап кеткенше екінші рет таңдау болмасын
        setDisabled(form, true);
        return pages
            .send(form, data)
            .then(function (reply) {
                if (!reply) {
                    return;
                }
                if (!reply.ok) {
                    setDisabled(form, false);
                    pages.showError(number, reply.result.error);
                    return;
                }
                showFeedback(form, number, reply.result);
            })
            .catch(function () {
                // Желі қатесі: жауап сақталмады — қайта таңдауға рұқсат
                form.querySelectorAll("input[type=radio]").forEach(function (input) {
                    input.checked = false;
                });
                setDisabled(form, false);
                pages.showError(number, pages.networkError);
            });
    });
})();
