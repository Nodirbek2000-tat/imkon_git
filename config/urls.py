from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from apps.artisans.views import ArtisanViewSet, PostViewSet
from apps.auctions.views import AuctionViewSet
from apps.catalog.views import CategoryViewSet, ProductViewSet
from apps.orders.views import CartViewSet, OrderViewSet
from apps.payments.urls import bot_urlpatterns

router = DefaultRouter()
router.register("products", ProductViewSet, basename="product")
router.register("categories", CategoryViewSet, basename="category")
router.register("artisans", ArtisanViewSet, basename="artisan")
router.register("posts", PostViewSet, basename="post")
router.register("auctions", AuctionViewSet, basename="auction")
router.register("cart", CartViewSet, basename="cart")
router.register("orders", OrderViewSet, basename="order")

urlpatterns = [
    # Django admini `/admin/` da EMAS: saytning o'z admin paneli ham shu
    # manzilda (`imkon_next/app/admin`). Ikkalasi bitta domenda turgani
    # uchun Django'niki boshqa yo'lga ko'chirildi.
    path("tizim-admin/", admin.site.urls),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/admin-panel/", include("apps.administration.urls")),
    path("api/notifications/", include("apps.notifications.urls")),
    path("api/balance/", include("apps.payments.urls")),
    path("api/bot/", include((bot_urlpatterns, "payments"), namespace="bot")),
    path("api/", include("apps.artisans.urls")),
    path("api/", include(router.urls)),
    # Hujjatlar: /api/docs/
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
