from django.urls import path

from .views import ApplicationView, CraftListView, MyShopView

app_name = "artisans"

urlpatterns = [
    path("crafts/", CraftListView.as_view(), name="crafts"),
    path("shop/apply/", ApplicationView.as_view(), name="apply"),
    path("shop/me/", MyShopView.as_view(), name="my-shop"),
]
