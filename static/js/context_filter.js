// Сұрақ формасы: тіл таңдалғанда «Контекст» тізімінде тек сол тілдегі
// контексттерді қалдырады (<option data-language="...">).
// Бұл тек ыңғайлылық үшін: контекст пен сұрақ тілінің сәйкестігін сервер тексереді.
document.addEventListener("DOMContentLoaded", function () {
    const contextSelect = document.getElementById("id_context");
    const languageInputs = document.querySelectorAll('input[name="language"]');
    if (!contextSelect || languageInputs.length === 0) {
        return;
    }

    function filterContexts() {
        const checked = document.querySelector('input[name="language"]:checked');
        const language = checked ? checked.value : "";
        for (const option of contextSelect.options) {
            if (!option.value) {
                continue; // «Жоқ (жеке сұрақ)» әрқашан көрінеді
            }
            const visible = !language || option.dataset.language === language;
            option.hidden = !visible;
            option.disabled = !visible;
        }
        // Таңдалған контекст басқа тілде болса — таңдауды тазалаймыз
        const selected = contextSelect.options[contextSelect.selectedIndex];
        if (selected && selected.disabled) {
            contextSelect.value = "";
        }
    }

    for (const input of languageInputs) {
        input.addEventListener("change", filterContexts);
    }
    filterContexts();
});
