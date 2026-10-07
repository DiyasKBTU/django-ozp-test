// Тақырып таңдалғанда тек соның тақырыпшаларын қалдырады (<option data-topic="...">).
// Бұл тек ыңғайлылық үшін: тақырыпшаның тақырыпқа жататынын сервер тексереді.
document.addEventListener("DOMContentLoaded", function () {
    const topicSelect = document.getElementById("id_topic");
    const subtopicSelect = document.getElementById("id_subtopic");
    if (!topicSelect || !subtopicSelect) {
        return;
    }

    function filterSubtopics() {
        const topicId = topicSelect.value;
        for (const option of subtopicSelect.options) {
            if (!option.value) {
                continue; // бос жол ("---------") әрқашан көрінеді
            }
            const visible = !topicId || option.dataset.topic === topicId;
            option.hidden = !visible;
            option.disabled = !visible;
        }
        // Таңдалған тақырыпша басқа тақырыпқа жатса — таңдауды тазалаймыз
        const selected = subtopicSelect.options[subtopicSelect.selectedIndex];
        if (selected && selected.disabled) {
            subtopicSelect.value = "";
        }
    }

    topicSelect.addEventListener("change", filterSubtopics);
    filterSubtopics();
});
