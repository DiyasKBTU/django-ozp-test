from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _

from .models import Profile, StudyGroup


@admin.register(StudyGroup)
class StudyGroupAdmin(admin.ModelAdmin):
    list_display = ["name"]
    search_fields = ["name"]


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False


# Қолданушы бетінде профильді (топты) бірге көрсету
admin.site.unregister(User)


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    inlines = [ProfileInline]
    list_display = ["username", "first_name", "last_name", "group_name", "is_staff"]
    list_filter = ["is_staff", "is_superuser", "profile__group"]

    @admin.display(description=_("топ"))
    def group_name(self, obj):
        # Профилі жоқ қолданушы үшін де қате бермейді
        profile = getattr(obj, "profile", None)
        if profile and profile.group:
            return profile.group
        return "—"
