// Тест таймері (templates/quiz/_timer.html).
// Қалған секундтарды сервер береді (data-remaining), сондықтан студенттің
// компьютеріндегі сағат қате болса да таймер дұрыс. 0-ге жеткенде тестті
// аяқтау бетіне жібереді; мерзімді бәрібір сервер тексереді.
(function () {
    var timer = document.getElementById("timer");
    if (!timer) {
        return;
    }
    var endTime = Date.now() + Number(timer.dataset.remaining) * 1000;

    function pad(number) {
        return String(number).padStart(2, "0");
    }

    function tick() {
        var left = Math.max(0, Math.ceil((endTime - Date.now()) / 1000));
        var hours = Math.floor(left / 3600);
        var minutes = Math.floor((left % 3600) / 60);
        timer.textContent = hours + ":" + pad(minutes) + ":" + pad(left % 60);
        // Соңғы 5 минут — қызыл
        timer.classList.toggle("text-danger", left <= 300);
        if (left === 0) {
            clearInterval(intervalId);
            // 1 секунд күтеміз: сервердегі мерзім міндетті түрде өтіп үлгереді
            setTimeout(function () {
                window.location.href = timer.dataset.finishUrl;
            }, 1000);
        }
    }

    // Алдымен setInterval: бірінші tick() бірден 0 көрсе, оны тоқтата алады
    var intervalId = setInterval(tick, 1000);
    tick();
})();
