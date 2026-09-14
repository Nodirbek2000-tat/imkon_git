from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import PhoneOTP, TelegramLoginCode, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("phone", "full_name", "role", "is_phone_verified", "is_active", "created_at")
    list_filter = ("role", "is_phone_verified", "is_active", "is_staff", "language")
    search_fields = ("phone", "full_name", "email")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "updated_at", "last_login")

    fieldsets = (
        (None, {"fields": ("phone", "password")}),
        ("Profil", {"fields": ("full_name", "avatar", "bio", "email", "language")}),
        ("Bog'langan akkauntlar", {"fields": ("google_id", "telegram_id", "telegram_username")}),
        ("Maqom", {"fields": ("role", "is_phone_verified")}),
        ("Ruxsatlar", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Sanalar", {"fields": ("last_login", "created_at", "updated_at")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("phone", "full_name", "password1", "password2")}),
    )


@admin.register(PhoneOTP)
class PhoneOTPAdmin(admin.ModelAdmin):
    list_display = ("phone", "purpose", "attempts", "is_used", "expires_at", "created_at")
    list_filter = ("purpose", "is_used")
    search_fields = ("phone",)
    readonly_fields = ("phone", "code_hash", "purpose", "expires_at", "attempts", "is_used")

    def has_add_permission(self, request):
        return False


@admin.register(TelegramLoginCode)
class TelegramLoginCodeAdmin(admin.ModelAdmin):
    list_display = ("phone", "telegram_username", "is_used", "expires_at", "created_at")
    list_filter = ("is_used",)
    search_fields = ("phone", "telegram_username")
    readonly_fields = (
        "telegram_id", "telegram_username", "full_name", "phone",
        "code_hash", "expires_at", "is_used",
    )

    def has_add_permission(self, request):
        return False
