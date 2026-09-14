from django.contrib import admin

from .models import Auction, Bid


class BidInline(admin.TabularInline):
    model = Bid
    extra = 0
    readonly_fields = ("user", "amount", "created_at")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Auction)
class AuctionAdmin(admin.ModelAdmin):
    list_display = ("product", "current_price", "bids_count", "status", "start_at", "end_at")
    list_filter = ("status",)
    search_fields = ("product__title_uz",)
    readonly_fields = ("current_price", "bids_count", "winner")
    inlines = (BidInline,)
    actions = ("finalize_auctions",)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("product", "winner")

    @admin.action(description="Yakunlash — g'olibni aniqlash")
    def finalize_auctions(self, request, queryset):
        count = 0
        for auction in queryset:
            auction.finalize()
            count += 1
        self.message_user(request, f"{count} ta auksion tekshirildi.")


@admin.register(Bid)
class BidAdmin(admin.ModelAdmin):
    list_display = ("auction", "user", "amount", "created_at")
    search_fields = ("user__phone", "auction__product__title_uz")
    readonly_fields = ("auction", "user", "amount")

    def has_add_permission(self, request):
        return False
