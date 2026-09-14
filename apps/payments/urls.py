from django.urls import path

from apps.accounts.views import BotLoginCodeView

from . import views

app_name = "payments"

# Sayt uchun — JWT bilan. `/api/balance/…`
urlpatterns = [
    path("", views.MyBalanceView.as_view(), name="balance"),
    path(
        "transactions/",
        views.MyBalanceTransactionsView.as_view(),
        name="balance-transactions",
    ),
]

# Bot uchun — `X-Bot-Secret` bilan. `/api/bot/…`
#
# Botning butun API yuzasi shu ro'yxatda, garchi kirish kodi `accounts` da
# tursa ham — bot bitta joyga qaraydi, "bu endpoint qaysi ilovada" degan
# savol bot tomonda umuman tug'ilmasin.
bot_urlpatterns = [
    path("login-code/", BotLoginCodeView.as_view(), name="bot-login-code"),
    path("users/sync/", views.BotUserSyncView.as_view(), name="bot-user-sync"),
    path(
        "users/<int:telegram_id>/",
        views.BotUserDetailView.as_view(),
        name="bot-user",
    ),
    path(
        "users/<int:telegram_id>/orders/",
        views.BotOrderListView.as_view(),
        name="bot-orders",
    ),
    path(
        "users/<int:telegram_id>/orders/<str:order_number>/",
        views.BotOrderDetailView.as_view(),
        name="bot-order",
    ),
    path(
        "users/<int:telegram_id>/orders/<str:order_number>/pay/",
        views.BotStartPaymentView.as_view(),
        name="bot-pay",
    ),
    path(
        "users/<int:telegram_id>/balance/",
        views.BotBalanceView.as_view(),
        name="bot-balance",
    ),
    path(
        "payments/<int:pk>/receipt/",
        views.BotReceiptView.as_view(),
        name="bot-receipt",
    ),
    path(
        "payments/<int:pk>/channel-message/",
        views.BotChannelMessageView.as_view(),
        name="bot-channel-message",
    ),
    path(
        "payments/<int:pk>/approve/",
        views.BotReviewView.as_view(decision="approve"),
        name="bot-approve",
    ),
    path(
        "payments/<int:pk>/reject/",
        views.BotReviewView.as_view(decision="reject"),
        name="bot-reject",
    ),
]
