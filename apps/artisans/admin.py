from django.contrib import admin, messages
from django.utils import timezone

from .models import ArtisanApplication, ArtisanProfile, Craft, Post, PostImage


@admin.register(Craft)
class CraftAdmin(admin.ModelAdmin):
    list_display = ("name_uz", "name_ru", "name_en", "slug")
    prepopulated_fields = {"slug": ("name_uz",)}


@admin.register(ArtisanProfile)
class ArtisanProfileAdmin(admin.ModelAdmin):
    list_display = ("shop_name_uz", "user", "region", "products_count", "posts_count", "is_active")
    list_filter = ("is_active", "region", "crafts")
    search_fields = ("shop_name_uz", "user__phone", "user__full_name")
    filter_horizontal = ("crafts",)
    readonly_fields = ("products_count", "posts_count", "sold_count", "created_at")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user")


@admin.register(ArtisanApplication)
class ArtisanApplicationAdmin(admin.ModelAdmin):
    list_display = ("shop_name", "user", "craft", "status", "created_at")
    list_filter = ("status", "craft")
    search_fields = ("shop_name", "user__phone", "user__full_name")
    actions = ("approve", "reject")
    readonly_fields = ("created_at", "reviewed_at")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user", "craft")

    @admin.action(description="Tasdiqlash — do'kon ochiladi")
    def approve(self, request, queryset):
        approved = 0

        for application in queryset.filter(status=ArtisanApplication.Status.PENDING):
            profile, _ = ArtisanProfile.objects.get_or_create(
                user=application.user,
                defaults={
                    "shop_name_uz": application.shop_name,
                    "about_uz": application.description,
                    "region": application.region,
                },
            )
            profile.crafts.add(application.craft)

            application.user.promote_to_artisan()

            application.status = ArtisanApplication.Status.APPROVED
            application.reviewed_at = timezone.now()
            application.save(update_fields=["status", "reviewed_at", "updated_at"])
            approved += 1

        self.message_user(request, f"{approved} ta ariza tasdiqlandi.", messages.SUCCESS)

    @admin.action(description="Rad etish")
    def reject(self, request, queryset):
        count = queryset.filter(status=ArtisanApplication.Status.PENDING).update(
            status=ArtisanApplication.Status.REJECTED, reviewed_at=timezone.now()
        )
        self.message_user(request, f"{count} ta ariza rad etildi.", messages.WARNING)


class PostImageInline(admin.TabularInline):
    model = PostImage
    extra = 1


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("__str__", "artisan", "likes_count", "is_published", "created_at")
    list_filter = ("is_published",)
    search_fields = ("caption", "artisan__shop_name_uz")
    inlines = (PostImageInline,)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("artisan")
