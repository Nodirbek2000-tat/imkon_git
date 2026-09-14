from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    GoogleLinkView,
    GoogleLoginView,
    MeView,
    PasswordLoginView,
    SendOTPView,
    SetPasswordView,
    TelegramLinkView,
    TelegramLoginView,
    VerifyOTPView,
)

app_name = "accounts"

urlpatterns = [
    path("otp/send/", SendOTPView.as_view(), name="otp-send"),
    path("otp/verify/", VerifyOTPView.as_view(), name="otp-verify"),
    path("password/", PasswordLoginView.as_view(), name="password-login"),
    path("password/set/", SetPasswordView.as_view(), name="password-set"),
    path("google/", GoogleLoginView.as_view(), name="google"),
    path("google/link/", GoogleLinkView.as_view(), name="google-link"),
    path("telegram/verify/", TelegramLoginView.as_view(), name="telegram-verify"),
    path("telegram/link/", TelegramLinkView.as_view(), name="telegram-link"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("me/", MeView.as_view(), name="me"),
]
