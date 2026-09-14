from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "type", "title", "is_read", "created_at")
    list_filter = ("type", "is_read")
    search_fields = ("title", "body", "user__phone", "user__full_name")
    readonly_fields = ("user", "type", "title", "body", "link_url", "created_at")
