from django.contrib import admin

from .models import CartItem, Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    fields = ("title", "artisan", "price", "quantity")
    readonly_fields = ("title", "artisan", "price", "quantity")
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("order_number", "user", "total", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("order_number", "user__phone", "full_name", "phone")
    readonly_fields = ("order_number", "total", "created_at", "updated_at")
    inlines = (OrderItemInline,)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user")


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ("user", "product", "quantity", "created_at")
    search_fields = ("user__phone", "product__title_uz")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user", "product")
