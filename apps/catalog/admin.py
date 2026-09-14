from django.contrib import admin

from .models import Category, Product, ProductImage


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name_uz", "name_ru", "name_en", "parent", "order")
    list_editable = ("order",)
    prepopulated_fields = {"slug": ("name_uz",)}


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ("image", "alt_text", "is_main", "order")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("title_uz", "artisan", "category", "price", "sale_type", "status")
    list_filter = ("status", "sale_type", "category")
    search_fields = ("title_uz", "title_ru", "title_en", "artisan__shop_name_uz")
    inlines = (ProductImageInline,)
    readonly_fields = ("views_count", "created_at", "updated_at")

    fieldsets = (
        (None, {"fields": ("artisan", "category", "slug", "status", "sale_type")}),
        ("Nomi", {"fields": ("title_uz", "title_ru", "title_en")}),
        ("Tavsif", {"fields": ("description_uz", "description_ru", "description_en")}),
        ("Narx", {"fields": ("price", "stock")}),
        ("Statistika", {"fields": ("views_count", "created_at", "updated_at")}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("artisan", "category")
