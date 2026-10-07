// Формулаларды KaTeX арқылы көрсетеді (templates/quiz/_katex.html).
// Белгілеу: \( ... \) — жол ішінде, \[ ... \] — бөлек жолда; $ қолданылмайды.
// Сұрақ, контекст мәтіні және жауап нұсқалары (<pre class="answer-text">) өңделеді;
// бағдарлама коды (<pre class="code-block">), <code> және форма өрістері өзгермейді.
// KaTeX жүктелмесе (желі жоқ), мәтін бастапқы күйінде қалады — тест тоқтамайды.
document.addEventListener("DOMContentLoaded", function () {
    if (typeof renderMathInElement !== "function") {
        return;
    }
    renderMathInElement(document.querySelector("main") || document.body, {
        delimiters: [
            { left: "\\(", right: "\\)", display: false },
            { left: "\\[", right: "\\]", display: true },
        ],
        ignoredTags: ["script", "noscript", "style", "textarea", "option", "code"],
        ignoredClasses: ["code-block"],
        throwOnError: false,
    });
});
