"""
To'lov API'lari.

Ikki auditoriya, ikki xil ruxsat:
  • `/api/bot/…`   — bot, `X-Bot-Secret` kaliti bilan (`IsBot`)
  • `/api/balance/…` — sayt, JWT bilan (sotuvchining o'z balansi)

Bot Telegramning o'zi bilan ishlaydi (xabar, rasm, tugma) — bu yerda
`requests` ham, `aiogram` ham yo'q. Backend faqat holatni biladi.
"""

from django.conf import settings
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.orders.models import Order

from apps.common.permissions import IsBot

from .models import Balance, BalanceTransaction, Payment
from .serializers import (
    BalanceSerializer,
    BalanceTransactionSerializer,
    BotOrderSerializer,
    BotUserSyncSerializer,
    ChannelMessageSerializer,
    PaymentSerializer,
    ReceiptSerializer,
    ReviewSerializer,
)
from .services import (
    PaymentError,
    approve_payment,
    attach_receipt,
    reject_payment,
    start_payment,
)


def _orders_qs():
    return Order.objects.prefetch_related(
        "items",
        Prefetch("payments", queryset=Payment.objects.select_related("card")),
    )


def _bot_user(telegram_id: int) -> User:
    user = User.objects.filter(telegram_id=telegram_id).first()
    if user is None:
        raise PermissionDenied("Bu Telegram akkaunt saytda ro'yxatdan o'tmagan.")
    return user


def _resolve_admin(telegram_id: int) -> User | None:
    """
    Kanalda tugma bosgan odam haqiqatan adminmi?

    Ikki yo'l bilan tekshiriladi: saytdagi `is_staff` akkaunt yoki `.env`
    dagi ro'yxat. Ikkinchisi shuning uchun kerakki, birinchi to'lov
    kelganda hali hech kim Telegram akkauntini saytga bog'lamagan bo'lishi
    mumkin — u holda to'lovni umuman hech kim tasdiqlay olmasdi.
    """
    user = User.objects.filter(telegram_id=telegram_id).first()
    if user and user.is_staff:
        return user
    if str(telegram_id) in settings.TELEGRAM_ADMIN_IDS:
        return user  # akkaunt bog'lanmagan bo'lsa `None` — amal baribir bajariladi
    raise PermissionDenied("Sizda to'lovni ko'rib chiqish huquqi yo'q.")


# ================================================================== bot


class BotUserSyncView(APIView):
    """
    Botda ro'yxatdan o'tish / kirish.

    Telefon raqami Telegramning o'z "kontakt yuborish" tugmasidan keladi —
    ya'ni raqam Telegram tomonidan tasdiqlangan, SMS kod kerak emas.

    Uch holat bor:
      • raqam ham, telegram_id ham yangi   → yangi akkaunt
      • raqam bor, telegram_id bog'lanmagan → bog'lanadi (sayt akkaunti bilan bir xil)
      • telegram_id allaqachon bor          → ma'lumot yangilanadi
    """

    permission_classes = (IsBot,)
    authentication_classes = ()

    def post(self, request):
        serializer = BotUserSyncSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        telegram_id = data["telegram_id"]
        phone = data["phone"]

        user = User.objects.filter(telegram_id=telegram_id).first()
        created = False

        if user is None:
            user = User.objects.filter(phone=phone).first()
            if user is None:
                user = User.objects.create_user(
                    phone=phone,
                    full_name=data["full_name"],
                    telegram_id=telegram_id,
                    telegram_username=data["telegram_username"],
                    is_phone_verified=True,
                )
                created = True
            else:
                # Sayt akkaunti bor — Telegramni shunga bog'laymiz.
                # Boshqa telegram_id bog'langan bo'lsa ustidan yozmaymiz.
                if user.telegram_id and user.telegram_id != telegram_id:
                    raise PermissionDenied(
                        "Bu raqamga boshqa Telegram akkaunt bog'langan."
                    )
                user.telegram_id = telegram_id
                user.telegram_username = data["telegram_username"]
                user.is_phone_verified = True
                user.save(
                    update_fields=[
                        "telegram_id", "telegram_username",
                        "is_phone_verified", "updated_at",
                    ]
                )
        else:
            user.telegram_username = data["telegram_username"]
            if not user.full_name:
                user.full_name = data["full_name"]
            user.save(update_fields=["telegram_username", "full_name", "updated_at"])

        return Response(
            {
                "id": user.id,
                "full_name": user.full_name,
                "phone": user.phone,
                "role": user.role,
                "is_artisan": user.is_artisan,
                "is_new": created,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class BotUserDetailView(APIView):
    """
    Bot `/start` da so'raydi: bu odam tanishmi?

    Topilmasa 404 — bot telefon raqami so'raydi. `_bot_user` ishlatilmaydi,
    chunki bu yerda "yo'q" javobi xato emas, oddiy holat.
    """

    permission_classes = (IsBot,)
    authentication_classes = ()

    def get(self, request, telegram_id):
        user = get_object_or_404(User, telegram_id=telegram_id)
        return Response(
            {
                "id": user.id,
                "full_name": user.full_name,
                "phone": user.phone,
                "role": user.role,
                "is_artisan": user.is_artisan,
            }
        )


class BotOrderListView(APIView):
    """Foydalanuvchining to'lanmagan buyurtmalari."""

    permission_classes = (IsBot,)
    authentication_classes = ()

    def get(self, request, telegram_id):
        user = _bot_user(telegram_id)
        orders = _orders_qs().filter(user=user, status=Order.Status.PENDING)
        return Response(BotOrderSerializer(orders, many=True).data)


class BotOrderDetailView(APIView):
    permission_classes = (IsBot,)
    authentication_classes = ()

    def get(self, request, telegram_id, order_number):
        user = _bot_user(telegram_id)
        order = get_object_or_404(_orders_qs(), order_number=order_number, user=user)
        return Response(BotOrderSerializer(order).data)


class BotStartPaymentView(APIView):
    """Xaridor "To'lov qilish" tugmasini bosdi — karta ma'lumotini qaytaradi."""

    permission_classes = (IsBot,)
    authentication_classes = ()

    def post(self, request, telegram_id, order_number):
        user = _bot_user(telegram_id)
        order = get_object_or_404(_orders_qs(), order_number=order_number, user=user)

        try:
            payment = start_payment(order)
        except PaymentError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        if payment.card is None:
            return Response(
                {"detail": "To'lov kartasi sozlanmagan. Admin bilan bog'laning."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(PaymentSerializer(payment).data)


class BotReceiptView(APIView):
    """Chek rasmi keldi — admin tekshiruviga o'tkazamiz."""

    permission_classes = (IsBot,)
    authentication_classes = ()

    def post(self, request, pk):
        payment = get_object_or_404(
            Payment.objects.select_related("order__user"), pk=pk
        )
        serializer = ReceiptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            attach_receipt(payment, file_id=serializer.validated_data["file_id"])
        except PaymentError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        order = _orders_qs().get(pk=payment.order_id)
        return Response(
            {
                "payment": PaymentSerializer(payment).data,
                "order": BotOrderSerializer(order).data,
                "buyer_telegram_id": payment.order.user.telegram_id,
            }
        )


class BotChannelMessageView(APIView):
    """Bot chekni kanalga yubordi — xabar raqamini eslab qolamiz."""

    permission_classes = (IsBot,)
    authentication_classes = ()

    def post(self, request, pk):
        payment = get_object_or_404(Payment, pk=pk)
        serializer = ChannelMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        payment.channel_message_id = serializer.validated_data["message_id"]
        payment.save(update_fields=["channel_message_id", "updated_at"])
        return Response({"ok": True})


class BotReviewView(APIView):
    """Kanaldagi "Tasdiqlash" / "Rad etish" tugmasi."""

    permission_classes = (IsBot,)
    authentication_classes = ()
    decision = None  # "approve" yoki "reject"

    def post(self, request, pk):
        payment = get_object_or_404(
            Payment.objects.select_related("order__user"), pk=pk
        )
        serializer = ReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        admin = _resolve_admin(serializer.validated_data["admin_telegram_id"])

        try:
            if self.decision == "approve":
                approve_payment(payment, admin=admin)
            else:
                reject_payment(
                    payment, admin=admin, reason=serializer.validated_data["reason"]
                )
        except PaymentError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        payment.refresh_from_db()
        order = _orders_qs().get(pk=payment.order_id)
        return Response(
            {
                "payment": PaymentSerializer(payment).data,
                "order": BotOrderSerializer(order).data,
                "buyer_telegram_id": payment.order.user.telegram_id,
                "reviewed_by": admin.full_name if admin else "",
            }
        )


class BotBalanceView(APIView):
    """Sotuvchi botda balansini ko'radi."""

    permission_classes = (IsBot,)
    authentication_classes = ()

    def get(self, request, telegram_id):
        user = _bot_user(telegram_id)
        balance = Balance.for_user(user)
        transactions = balance.transactions.select_related("order")[:10]
        return Response(
            {
                "balance": BalanceSerializer(balance).data,
                "transactions": BalanceTransactionSerializer(transactions, many=True).data,
            }
        )


# ================================================================== sayt


class MyBalanceView(APIView):
    """Profildagi "Balans" bo'limi."""

    permission_classes = (IsAuthenticated,)

    def get(self, request):
        balance = Balance.for_user(request.user)
        return Response(BalanceSerializer(balance).data)


class MyBalanceTransactionsView(ListAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = BalanceTransactionSerializer

    def get_queryset(self):
        balance = Balance.for_user(self.request.user)
        return BalanceTransaction.objects.filter(balance=balance).select_related("order")
