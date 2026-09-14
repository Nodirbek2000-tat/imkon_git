from django.contrib import admin, messages
from django.utils.html import format_html

from .models import Balance, BalanceTransaction, Payment, PaymentCard
from .services import PaymentError, approve_payment, reject_payment


@admin.register(PaymentCard)
class PaymentCardAdmin(admin.ModelAdmin):
    list_display = ("number", "holder_name", "bank", "is_active")
    list_filter = ("is_active", "bank")
    search_fields = ("number", "holder_name")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("order", "amount", "status", "receipt_preview", "reviewed_by", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("order__order_number", "order__phone")
    readonly_fields = (
        "order", "card", "amount", "receipt_file_id", "receipt_preview",
        "receipt_sent_at", "channel_message_id", "reviewed_by", "reviewed_at",
    )
    actions = ("action_approve", "action_reject")

    @admin.display(description="Chek")
    def receipt_preview(self, obj):
        if not obj.receipt_image:
            return "—" if not obj.receipt_file_id else "Telegramda"
        return format_html(
            '<a href="{}" target="_blank">Ochish</a>', obj.receipt_image.url
        )

    def _run(self, request, queryset, func, **kwargs):
        done = 0
        for payment in queryset:
            try:
                func(payment, admin=request.user, **kwargs)
                done += 1
            except PaymentError as exc:
                self.message_user(request, f"{payment}: {exc}", messages.WARNING)
        if done:
            self.message_user(request, f"{done} ta to'lov qayta ishlandi.", messages.SUCCESS)

    @admin.action(description="Tasdiqlash (balansga o'tkazish)")
    def action_approve(self, request, queryset):
        self._run(request, queryset, approve_payment)

    @admin.action(description="Rad etish")
    def action_reject(self, request, queryset):
        self._run(request, queryset, reject_payment, reason="Admin panelidan rad etildi")


class BalanceTransactionInline(admin.TabularInline):
    model = BalanceTransaction
    extra = 0
    can_delete = False
    readonly_fields = (
        "type", "order", "gross_amount", "commission_amount",
        "amount", "balance_after", "comment", "created_at",
    )

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Balance)
class BalanceAdmin(admin.ModelAdmin):
    list_display = ("user", "amount", "updated_at")
    search_fields = ("user__phone", "user__full_name")
    readonly_fields = ("user", "amount")
    inlines = (BalanceTransactionInline,)


@admin.register(BalanceTransaction)
class BalanceTransactionAdmin(admin.ModelAdmin):
    list_display = ("balance", "type", "gross_amount", "commission_amount", "amount", "created_at")
    list_filter = ("type", "created_at")
    search_fields = ("balance__user__phone", "order__order_number")

    def has_change_permission(self, request, obj=None):
        # Pul tarixi tahrirlanmaydi — faqat o'qish uchun
        return False
