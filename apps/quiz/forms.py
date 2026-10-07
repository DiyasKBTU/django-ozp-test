from django import forms
from django.utils.translation import gettext_lazy as _

from .constants import ANSWERS_PER_QUESTION


class AnswerInlineFormSet(forms.BaseInlineFormSet):
    """
    Сұрақтың жауап нұсқаларын тексереді:
    дәл 4 нұсқа және олардың дәл біреуі дұрыс.
    """

    def clean(self):
        super().clean()
        if any(self.errors):
            return

        filled_count = 0
        correct_count = 0
        for form in self.forms:
            # Жойылатын немесе бос қалған жолдарды санамаймыз
            if not form.cleaned_data or form.cleaned_data.get("DELETE"):
                continue
            filled_count += 1
            if form.cleaned_data.get("is_correct"):
                correct_count += 1

        if filled_count != ANSWERS_PER_QUESTION:
            raise forms.ValidationError(
                _("Дәл %(count)s жауап нұсқасы болуы керек.")
                % {"count": ANSWERS_PER_QUESTION}
            )
        if correct_count != 1:
            raise forms.ValidationError(_("Дәл бір дұрыс жауап белгіленуі керек."))
