// Тест беті (templates/quiz/question.html): бетті қайта жүктемей жұмыс істеу.
// - Барлық сұрақ бетте бар, біреуі ғана көрінеді: навигация, «Алдыңғы» / «Келесі»
//   сілтемелері сұрақты ауыстырады, мекенжай (URL) да жаңарады.
// - Жауап таңдалғанда форма AJAX (fetch) арқылы жіберіледі, сервер JSON қайтарады.
//   Жауаптар кезекпен жіберіледі — соңғы таңдау серверде де соңғы болып сақталады.
// - Мерзімді бәрібір сервер тексереді: уақыт өтсе, сервер нәтиже бетіне жібереді.
// JS жоқ болса, сілтемелер мен формалар бұрынғыдай (бет қайта жүктеледі) жұмыс істейді.
(function () {
    var page = document.getElementById("attempt-page");
    if (!page || !window.fetch || !window.FormData) {
        return;
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

    // ---------- Сұрақтар арасында ауысу ----------

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
        // «Тестті аяқтау»: алдымен жіберіліп жатқан жауаптар сақталсын
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

    // ---------- Жауапты сақтау ----------

    function markSelected(form, answerId) {
        form.querySelectorAll("label").forEach(function (label) {
            var input = label.querySelector("input");
            var selected = answerId !== "" && input.value === answerId;
            input.checked = selected;
            label.classList.toggle("active", selected);
        });
    }

    function setMessage(number, saved, error) {
        var section = block(number);
        section.querySelector(".answer-saved").classList.toggle("d-none", !saved);
        var errorBox = section.querySelector(".answer-error");
        errorBox.textContent = error || "";
        errorBox.classList.toggle("d-none", !error);
    }

    function save(form, data) {
        var number = Number(form.dataset.number);
        return fetch(form.action, {
            method: "POST",
            body: data,
            credentials: "same-origin",
            headers: { "X-Requested-With": "XMLHttpRequest" },
        })
            .then(function (response) {
                var type = response.headers.get("Content-Type") || "";
                if (type.indexOf("application/json") === -1) {
                    // Мысалы, кіру сессиясы бітті — бетті толық ашамыз
                    window.location.href = form.action;
                    return null;
                }
                return response.json().then(function (result) {
                    return { ok: response.ok, result: result };
                });
            })
            .then(function (reply) {
                if (!reply) {
                    return;
                }
                if (reply.result.redirect) {
                    // Уақыт бітті немесе тест аяқталған — нәтиже бетіне
                    window.location.href = reply.result.redirect;
                    return;
                }
                if (!reply.ok) {
                    markSelected(form, form.dataset.saved);
                    setMessage(number, form.dataset.saved !== "", reply.result.error);
                    return;
                }
                form.dataset.saved = data.get("answer");
                navLink(number).classList.remove("btn-outline-secondary");
                navLink(number).classList.add("btn-primary");
                document.getElementById("unanswered-count").textContent = reply.result.unanswered;
                setMessage(number, true, "");
            })
            .catch(function () {
                // Желі қатесі: экрандағы таңдауды серверде сақталғанына қайтарамыз
                markSelected(form, form.dataset.saved);
                setMessage(number, form.dataset.saved !== "", page.dataset.networkError);
            });
    }

    // Радио-батырма requestSubmit() шақырады — жіберуді осы жерде ұстап, AJAX-пен жібереміз
    page.addEventListener("submit", function (event) {
        var form = event.target.closest("form.answer-form");
        if (!form) {
            return;
        }
        event.preventDefault();
        var data = new FormData(form);
        markSelected(form, data.get("answer") || "");
        queue = queue.then(function () {
            return save(form, data);
        });
    });
})();
