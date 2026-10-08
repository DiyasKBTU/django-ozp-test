from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _

from apps.quiz.admin import TeacherSubjectAdminMixin

from .forms import ProfileInlineFormSet
from .models import Profile, StudyGroup


@admin.register(StudyGroup)
class StudyGroupAdmin(TeacherSubjectAdminMixin, admin.ModelAdmin):
    list_display = ["name", "subject", "language"]
    list_filter = ["subject", "language"]
    search_fields = ["name"]


class ProfileInline(admin.StackedInline):
    model = Profile
    formset = ProfileInlineFormSet
    can_delete = False
    # Пәндер тек оқытушыға тағайындалады
    filter_horizontal = ["subjects"]


# Қолданушы бетінде профильді (топ, пәндер) бірге көрсету
admin.site.unregister(User)


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    """
    Оқытушы тек осы жерде қосылады (сайтта тек студент тіркеледі): әкімші
    бір бетте логин, құпия сөз, аты-жөнін енгізіп, «Қызметкер мәртебесі»
    (is_staff) белгілейді және төмендегі профильде пәндерін таңдайды.
    """

    inlines = [ProfileInline]
    add_fieldsets = (
        (None, {"fields": ("username", "usable_password", "password1", "password2")}),
        (_("Аты-жөні"), {"fields": ("first_name", "last_name")}),
        (
            _("Оқытушы"),
            {
                "fields": ("is_staff",),
                "description": _(
                    "Оқытушы болса белгілеңіз және төмендегі профильде пәндерін таңдаңыз."
                ),
            },
        ),
    )
    list_display = ["username", "first_name", "last_name", "group_name", "is_staff"]
    list_filter = ["is_staff", "is_superuser", "profile__subjects", "profile__group"]

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        user = form.instance
        # Пәні жоқ оқытушы /teacher/ беттерінде тек «пән тағайындалмаған» хабарламасын көреді
        if user.is_staff and not user.is_superuser and not user.profile.subjects.exists():
            messages.warning(
                request,
                _("%(user)s — оқытушы, бірақ оған пән тағайындалмаған.") % {"user": user},
            )

    @admin.display(description=_("топ"))
    def group_name(self, obj):
        # Профилі жоқ қолданушы үшін де қате бермейді
        profile = getattr(obj, "profile", None)
        if profile and profile.group:
            return profile.group
        return "—"
