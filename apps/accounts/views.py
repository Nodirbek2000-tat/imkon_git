from django.conf import settings
from django.contrib.auth import authenticate
from django.db import IntegrityError, transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.common.permissions import IsBot

from .google import GoogleAuthError, verify_google_token
from .models import PhoneOTP, TelegramLoginCode, User
from .serializers import (
    BotLoginCodeSerializer,
    GoogleLoginSerializer,
    PasswordLoginSerializer,
    SendOTPSerializer,
    SetPasswordSerializer,
    TelegramCodeSerializer,
    TokenPairSerializer,
    UserSerializer,
    VerifyOTPSerializer,
)
from .sms import SMSError, send_otp


def _tokens_for(user: User) -> dict:
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


class SendOTPView(APIView):
    """
    1-qadam: raqamga kod yuborish.

    Ro'yxatdan o'tish ham, kirish ham shu bitta endpoint orqali —
    foydalanuvchi uchun farqi yo'q.
    """

    permission_classes = (AllowAny,)
    throttle_scope = "otp_send"

    @extend_schema(request=SendOTPSerializer, responses={200: None})
    def post(self, request):
        serializer = SendOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data["phone"]

        otp, code = PhoneOTP.issue(phone)

        try:
            send_otp(phone, code)
        except SMSError as exc:
            # Yuborilmagan kodni bazada qoldirmaymiz
            otp.delete()
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        return Response(
            {
                "detail": "Kod yuborildi.",
                "expires_in": int((otp.expires_at - timezone.now()).total_seconds()),
                "phone": phone,
            }
        )


class VerifyOTPView(APIView):
    """
    2-qadam: kodni tekshirish → JWT.

    Raqam bazada bo'lmasa yangi akkaunt ochiladi (maqom: `user`).
    """

    permission_classes = (AllowAny,)
    throttle_scope = "otp_verify"

    @extend_schema(request=VerifyOTPSerializer, responses={200: TokenPairSerializer})
    def post(self, request):
        serializer = VerifyOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data["phone"]
        code = serializer.validated_data["code"]

        otp = (
            PhoneOTP.objects.filter(phone=phone, purpose=PhoneOTP.Purpose.LOGIN, is_used=False)
            .order_by("-created_at")
            .first()
        )
        if otp is None:
            return Response(
                {"detail": "Faol kod topilmadi. Qaytadan so'rang."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ok, message = otp.verify(code)
        if not ok:
            return Response({"detail": message}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            user, is_new = User.objects.get_or_create(
                phone=phone,
                defaults={
                    "full_name": serializer.validated_data.get("full_name", ""),
                    "is_phone_verified": True,
                },
            )
            if not user.is_phone_verified:
                user.is_phone_verified = True
                user.save(update_fields=["is_phone_verified", "updated_at"])

        return Response(
            {
                **_tokens_for(user),
                "user": UserSerializer(user, context={"request": request}).data,
                "is_new": is_new,
            }
        )


class PasswordLoginView(APIView):
    """
    Login (telefon) + parol bilan kirish.

    Parol faqat foydalanuvchi o'zi profilida o'rnatgan bo'lsa ishlaydi
    (`SetPasswordView`) — boshqa hech kim uchun parol avtomatik
    o'rnatilmaydi (`UserManager.create_user` parolsiz bo'lsa
    `set_unusable_password()` chaqiradi, shu hisobga hech qanday parol
    bilan kirib bo'lmaydi).
    """

    permission_classes = (AllowAny,)
    throttle_scope = "password_login"

    @extend_schema(request=PasswordLoginSerializer, responses={200: TokenPairSerializer})
    def post(self, request):
        serializer = PasswordLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = authenticate(
            request,
            username=serializer.validated_data["phone"],
            password=serializer.validated_data["password"],
        )
        if user is None:
            return Response(
                {"detail": "Login yoki parol noto'g'ri."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not user.is_active:
            return Response(
                {"detail": "Akkaunt bloklangan."}, status=status.HTTP_403_FORBIDDEN
            )

        return Response(
            {
                **_tokens_for(user),
                "user": UserSerializer(user, context={"request": request}).data,
                "is_new": False,
            }
        )


class GoogleLoginView(APIView):
    """
    Google orqali kirish.

    Frontend Google'dan ID token oladi va shu yerga yuboradi.
    Token Google kalitlari bilan tekshiriladi.
    """

    permission_classes = (AllowAny,)

    @extend_schema(request=GoogleLoginSerializer, responses={200: TokenPairSerializer})
    def post(self, request):
        serializer = GoogleLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            profile = verify_google_token(serializer.validated_data["credential"])
        except GoogleAuthError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            user = User.objects.filter(google_id=profile["google_id"]).first()
            is_new = False

            if user is None:
                # Shu email bilan telefon orqali ochilgan akkaunt bormi?
                # Bo'lsa — ikkitasini bog'laymiz, dublikat yaratmaymiz.
                if profile["email"]:
                    user = User.objects.filter(email__iexact=profile["email"]).first()

                if user is not None:
                    user.google_id = profile["google_id"]
                    user.save(update_fields=["google_id", "updated_at"])
                else:
                    user = User.objects.create_user(
                        phone=None,
                        google_id=profile["google_id"],
                        email=profile["email"],
                        full_name=profile["full_name"],
                    )
                    is_new = True

        return Response(
            {
                **_tokens_for(user),
                "user": UserSerializer(user, context={"request": request}).data,
                "is_new": is_new,
                # Telefon yo'q bo'lsa frontend uni so'raydi — SMS xabarlar
                # (auksion yutug'i, ariza javobi) shusiz yetib bormaydi
                "needs_phone": not user.phone,
            }
        )


class BotLoginCodeView(APIView):
    """
    Bot saytga kirish uchun bir martalik kod so'raydi.

    Kodni bot emas, backend yaratadi — bot bazaga umuman tegmaydi. Xom kod
    faqat shu javobda ko'rinadi, bazada esa hash saqlanadi.

    Telefon raqami Telegramning "kontakt yuborish" tugmasidan keladi, ya'ni
    Telegram tomonidan tasdiqlangan — shuning uchun SMS kod talab qilinmaydi.
    """

    permission_classes = (IsBot,)
    authentication_classes = ()

    @extend_schema(request=BotLoginCodeSerializer, responses={200: dict})
    def post(self, request):
        serializer = BotLoginCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        _obj, code = TelegramLoginCode.issue(
            telegram_id=data["telegram_id"],
            telegram_username=data["telegram_username"],
            full_name=data["full_name"],
            phone=data["phone"],
        )

        return Response(
            {"code": code, "ttl_seconds": settings.TELEGRAM_CODE_TTL_SECONDS}
        )


class TelegramLoginView(APIView):
    """
    Telegram bot orqali kirish/ro'yxatdan o'tish.

    Bot foydalanuvchining telefon raqamini (Telegram o'zi tasdiqlagan) va
    5 daqiqalik kodni beradi. Sayt shu yerga faqat kodni yuboradi.
    """

    permission_classes = (AllowAny,)
    throttle_scope = "telegram_verify"

    @extend_schema(request=TelegramCodeSerializer, responses={200: TokenPairSerializer})
    def post(self, request):
        serializer = TelegramCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        code_obj = TelegramLoginCode.consume(serializer.validated_data["code"])
        if code_obj is None:
            return Response(
                {"detail": "Kod noto'g'ri yoki muddati tugagan. Botdan qaytadan so'rang."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            user = User.objects.filter(telegram_id=code_obj.telegram_id).first()
            is_new = False

            if user is None:
                # Shu raqam bilan avval SMS orqali ochilgan akkaunt bormi?
                # Bo'lsa bog'laymiz, dublikat yaratmaymiz — Telegram tasdiqlagan
                # raqam kamida SMS orqali kiritilgan raqam kabi ishonchli
                user = User.objects.filter(phone=code_obj.phone).first()

                if user is not None:
                    user.telegram_id = code_obj.telegram_id
                    user.telegram_username = code_obj.telegram_username
                    user.save(update_fields=["telegram_id", "telegram_username", "updated_at"])
                else:
                    user = User.objects.create_user(
                        phone=code_obj.phone,
                        telegram_id=code_obj.telegram_id,
                        telegram_username=code_obj.telegram_username,
                        full_name=code_obj.full_name,
                        is_phone_verified=True,
                    )
                    is_new = True

        return Response(
            {
                **_tokens_for(user),
                "user": UserSerializer(user, context={"request": request}).data,
                "is_new": is_new,
            }
        )


class GoogleLinkView(APIView):
    """Tizimga kirgan foydalanuvchi profiliga Google akkauntini bog'laydi."""

    permission_classes = (IsAuthenticated,)

    @extend_schema(request=GoogleLoginSerializer, responses={200: UserSerializer})
    def post(self, request):
        serializer = GoogleLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            profile = verify_google_token(serializer.validated_data["credential"])
        except GoogleAuthError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        if (
            User.objects.filter(google_id=profile["google_id"])
            .exclude(pk=request.user.pk)
            .exists()
        ):
            return Response(
                {"detail": "Bu Google akkaunt allaqachon boshqa foydalanuvchiga bog'langan."},
                status=status.HTTP_409_CONFLICT,
            )

        user = request.user
        user.google_id = profile["google_id"]
        if not user.email:
            user.email = profile["email"]
        try:
            with transaction.atomic():
                user.save(update_fields=["google_id", "email", "updated_at"])
        except IntegrityError:
            # Poyga holati — pre-check'dan keyin boshqa so'rov ulgurgan bo'lishi mumkin
            return Response(
                {"detail": "Bu Google akkaunt allaqachon boshqa foydalanuvchiga bog'langan."},
                status=status.HTTP_409_CONFLICT,
            )

        return Response(UserSerializer(user, context={"request": request}).data)


class TelegramLinkView(APIView):
    """Tizimga kirgan foydalanuvchi profiliga Telegram akkauntini bog'laydi."""

    permission_classes = (IsAuthenticated,)

    @extend_schema(request=TelegramCodeSerializer, responses={200: UserSerializer})
    def post(self, request):
        serializer = TelegramCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        code_obj = TelegramLoginCode.consume(serializer.validated_data["code"])
        if code_obj is None:
            return Response(
                {"detail": "Kod noto'g'ri yoki muddati tugagan. Botdan qaytadan so'rang."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if (
            User.objects.filter(telegram_id=code_obj.telegram_id)
            .exclude(pk=request.user.pk)
            .exists()
        ):
            return Response(
                {"detail": "Bu Telegram akkaunt allaqachon boshqa foydalanuvchiga bog'langan."},
                status=status.HTTP_409_CONFLICT,
            )

        user = request.user
        update_fields = ["telegram_id", "telegram_username", "updated_at"]
        user.telegram_id = code_obj.telegram_id
        user.telegram_username = code_obj.telegram_username

        # Raqam bo'sh bo'lsa to'ldiramiz — lekin boshqa akkauntda band bo'lsa
        # butun so'rovni yiqitmaymiz, faqat raqamni to'ldirmay o'tamiz
        if not user.phone and not User.objects.filter(phone=code_obj.phone).exists():
            user.phone = code_obj.phone
            user.is_phone_verified = True
            update_fields += ["phone", "is_phone_verified"]

        try:
            with transaction.atomic():
                user.save(update_fields=update_fields)
        except IntegrityError:
            return Response(
                {"detail": "Bu Telegram akkaunt allaqachon boshqa foydalanuvchiga bog'langan."},
                status=status.HTTP_409_CONFLICT,
            )

        return Response(UserSerializer(user, context={"request": request}).data)


class SetPasswordView(APIView):
    """Tizimga kirgan foydalanuvchi o'ziga parol o'rnatadi/yangilaydi."""

    permission_classes = (IsAuthenticated,)

    @extend_schema(request=SetPasswordSerializer, responses={200: UserSerializer})
    def post(self, request):
        serializer = SetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        request.user.set_password(serializer.validated_data["password"])
        request.user.save(update_fields=["password"])

        return Response(UserSerializer(request.user, context={"request": request}).data)


class MeView(RetrieveUpdateAPIView):
    """O'z profilini ko'rish va tahrirlash (ism, bio, rasm, til)."""

    serializer_class = UserSerializer
    permission_classes = (IsAuthenticated,)

    def get_object(self):
        # artisan_profile birga yuklanadi — `artisan_slug` uchun qo'shimcha
        # so'rov ketmasin
        return (
            User.objects.select_related("artisan_profile")
            .get(pk=self.request.user.pk)
        )
