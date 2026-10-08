// Тест беті (attempt.js) мен жаттығу бетіне (practice.js) ортақ бөлік:
// бір беттегі сұрақтар арасында бетті қайта жүктемей ауысу және жауапты AJAX-пен жіберу.
//
// Беттің құрылымы (templates/quiz/question.html, practice_question.html):
//   <div id="question-page" data-current="N" data-total="50" data-network-error="...">
//   сұрақ — <section id="question-N" class="question-block" data-url="..." data-title="...">
//   ауысу сілтемелері — <a data-question="N">, навигация ұяшығы — data-nav="N",
//   «Тестті аяқтау» / «Қорытынды» — <a class="finish-link">.
// JS жоқ болса (немесе браузер ескі болса) бұл файл ештеңе істемейді — сілтемелер мен
// формалар бұрынғыдай, бетті қайта жүктеп жұмыс істейді.
window.QuestionPages = (function () {
    var page = document.getElementById("question-page");
    if (!page || !window.fetch || !window.FormData || !window.history.pushState) {
        return null;
    }
    var total = Number(page.dataset.total);
    var current = Number(page.dataset.current);
    // Жауаптарды сақтау кезегі: келесісі алдыңғысы біткен соң ғана жіберіледі
    var queue = Promise.resolve();

    function block(number) {
        return document.getElementById("question-" + number);
    }

    function navLink(number) {
        return page.querySelector('[data-nav="' + number + '"]');
    }

    function show(number, addToHistory) {
        if (!(number >= 1 && number <= total) || number === current) {
            return;
        }
        block(current).classList.add("d-none");
        navLink(current).classList.remove("border-3", "border-warning", "fw-bold");
        navLink(current).removeAttribute("aria-current");

        var target = block(number);
        target.classList.remove("d-none");
        navLink(number).classList.add("border-3", "border-warning", "fw-bold");
        navLink(number).setAttribute("aria-current", "page");
        current = number;

        document.title = target.dataset.title;
        if (addToHistory) {
            history.pushState({ number: number }, "", target.dataset.url);
        }
        window.scrollTo(0, 0);
    }

    page.addEventListener("click", function (event) {
        var link = event.target.closest("a[data-question]");
        if (link) {
            event.preventDefault();
            show(Number(link.dataset.question), true);
            return;
        }
        // «Аяқтау» / «Қорытынды»: алдымен жіберіліп жатқан жауаптар сақталсын
        var finish = event.target.closest("a.finish-link");
        if (finish) {
            event.preventDefault();
            queue.then(function () {
                window.location.href = finish.href;
            });
        }
    });

    // Браузердің «Артқа» / «Алға» батырмалары
    window.addEventListener("popstate", function (event) {
        var number = event.state && event.state.number;
        if (!number) {
            var match = window.location.pathname.match(/\/q\/(\d+)\/$/);
            number = match ? Number(match[1]) : current;
        }
        show(Number(number), false);
    });
    history.replaceState({ number: current }, "", window.location.href);

    // Жауапты AJAX-пен жібереді. Нәтиже: {ok, result} (сервердің JSON жауабы) немесе null —
    // бет басқа мекенжайға кетті (сервер redirect айтты не JSON емес жауап келді).
    // Желі қатесінде promise қатемен аяқталады.
    function send(form, data) {
        return fetch(form.action, {
            method: "POST",
            body: data,
            credentials: "same-origin",
            headers: { "X-Requested-With": "XMLHttpRequest" },
        }).then(function (response) {
            var type = response.headers.get("Content-Type") || "";
            if (type.indexOf("application/json") === -1) {
                // Мысалы, кіру сессиясы бітті — бетті толық ашамыз
                window.location.href = form.action;
                return null;
            }
            return response.json().then(function (result) {
                if (result.redirect) {
                    window.location.href = result.redirect;
                    return null;
                }
                return { ok: response.ok, result: result };
            });
        });
    }

    // Форма жіберілгенде (радио-батырма requestSubmit() шақырады) — AJAX-пен кезекке қояды.
    // handle(form, data) — бетке тән өңдеуші (attempt.js / practice.js), promise қайтарады.
    function onAnswer(handle) {
        page.addEventListener("submit", function (event) {
            var form = event.target.closest("form.answer-form");
            if (!form) {
                return;
            }
            event.preventDefault();
            var data = new FormData(form);
            queue = queue.then(function () {
                return handle(form, data);
            });
        });
    }

    function showError(number, text) {
        var errorBox = block(number).querySelector(".answer-error");
        errorBox.textContent = text || "";
        errorBox.classList.toggle("d-none", !text);
    }

    return {
        page: page,
        block: block,
        navLink: navLink,
        send: send,
        onAnswer: onAnswer,
        showError: showError,
        networkError: page.dataset.networkError,
    };
})();
