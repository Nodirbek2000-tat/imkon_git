"""
To'lov jarayonining barcha mantiqi.

Bu yerda Telegram bilan hech qanday aloqa yo'q — atay. Bot Telegram
tomonini biladi (xabar yuborish, rasm, tugmalar), backend esa holatni
biladi (kim, qancha, tasdiqlandimi). Ikkisi orasidagi chegara `views.py`.

Shu bo'linish tufayli to'lovni admin panelidan ham, botdan ham, testdan
ham bir xil funksiya bilan tasdiqlash mumkin.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from apps.artisans.models import ArtisanProfile
from apps.catalog.models import Product
from apps.notifications.models import Notification
from apps.orders.models import Order, OrderItem

from .models import Balance, BalanceTransaction, Payment, PaymentCard

TIYIN = Decimal("0.01")


class PaymentError(Exception):
    """To'lov ustida noto'g'ri amal — sabab foydalanuvchiga ko'rsatiladi."""


def commission_for(amount: Decimal) -> Decimal:
    """Platforma ulushi. 100 000 so'mdan 5% = 5 000 so'm."""
    percent = Decimal(str(settings.PLATFORM_COMMISSION_PERCENT))
    return (amount * percent / Decimal("100")).quantize(TIYIN, rounding=ROUND_HALF_UP)


# ------------------------------------------------------------------ boshlash


def start_payment(order: Order) -> Payment:
    """
    Buyurtma uchun to'lov ochadi (yoki ochig'ini qaytaradi).

    Xaridor botda "To'lov qilish"ni ikki marta bossa yangi yozuv
    yaratilmasligi kerak — aks holda bitta buyurtma uchun kanalga ikkita
    chek so'rovi tushadi.
    """
    if order.status == Order.Status.PAID:
        raise PaymentError("Bu buyurtma allaqachon to'langan.")
    if order.status == Order.Status.CANCELLED:
        raise PaymentError("Buyurtma bekor qilingan.")

    with transaction.atomic():
        existing = (
            Payment.objects.select_for_update()
            .filter(order=order, status__in=Payment.OPEN_STATUSES)
            .first()
        )
        if existing:
            # Karta almashgan bo'lishi mumkin — ochiq to'lovda yangisini ko'rsatamiz
            card = PaymentCard.active()
            if card and existing.card_id != card.id and not existing.receipt_file_id:
                existing.card = card
                existing.save(update_fields=["card", "updated_at"])
            return existing

        return Payment.objects.create(
            order=order, card=PaymentCard.active(), amount=order.total
        )


def attach_receipt(payment: Payment, *, file_id: str) -> Payment:
    """Xaridor chek rasmini yubordi — admin tekshiruviga o'tadi."""
    if payment.status == Payment.Status.APPROVED:
        raise PaymentError("To'lov allaqachon tasdiqlangan.")
    if payment.status == Payment.Status.REJECTED:
        raise PaymentError("Bu to'lov rad etilgan. Yangi to'lov boshlang.")

    payment.receipt_file_id = file_id
    payment.receipt_sent_at = timezone.now()
    payment.status = Payment.Status.PENDING
    payment.save(
        update_fields=["receipt_file_id", "receipt_sent_at", "status", "updated_at"]
    )
    return payment


# ------------------------------------------------------------------ qaror


def approve_payment(payment: Payment, *, admin=None) -> Payment:
    """
    To'lovni tasdiqlaydi.

    Bitta atomik blokda uchta narsa bo'ladi: to'lov tasdiqlanadi, buyurtma
    `paid` bo'ladi, sotuvchilar balansiga pul o'tadi. Biri bajarilib
    ikkinchisi bajarilmay qolsa — pul yo'qoladi yoki ikki marta yoziladi.

    `select_for_update` — kanalda ikkita admin bir vaqtda "Tasdiqlash"
    bossa, ikkinchisi yangilangan holatni ko'radi va rad etiladi.
    """
    with transaction.atomic():
        payment = Payment.objects.select_for_update().select_related("order").get(pk=payment.pk)

        if payment.status == Payment.Status.APPROVED:
            raise PaymentError("Bu to'lov allaqachon tasdiqlangan.")
        if payment.status == Payment.Status.REJECTED:
            raise PaymentError("Bu to'lov rad etilgan.")

        payment.status = Payment.Status.APPROVED
        payment.reviewed_by = admin
        payment.reviewed_at = timezone.now()
        payment.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])

        order = payment.order
        order.status = Order.Status.PAID
        order.save(update_fields=["status", "updated_at"])

        _credit_sellers(order)
        _reserve_stock(order)

    _notify_approved(payment)
    return payment


def reject_payment(payment: Payment, *, admin=None, reason: str = "") -> Payment:
    """
    Chekni rad etadi.

    Buyurtma `pending` holatida qoladi — xaridor to'g'ri chek bilan qaytadan
    urinib ko'radi. Buyurtmani bekor qilish alohida amal.
    """
    with transaction.atomic():
        payment = Payment.objects.select_for_update().select_related("order").get(pk=payment.pk)

        if payment.status == Payment.Status.APPROVED:
            raise PaymentError("Tasdiqlangan to'lovni rad etib bo'lmaydi.")
        if payment.status == Payment.Status.REJECTED:
            raise PaymentError("Bu to'lov allaqachon rad etilgan.")

        payment.status = Payment.Status.REJECTED
        payment.reviewed_by = admin
        payment.reviewed_at = timezone.now()
        payment.reject_reason = reason[:300]
        payment.save(
            update_fields=[
                "status", "reviewed_by", "reviewed_at", "reject_reason", "updated_at",
            ]
        )

    _notify_rejected(payment)
    return payment


# ------------------------------------------------------------------ ichki


def _credit_sellers(order: Order) -> None:
    """
    Har bir sotuvchiga o'z mahsuloti uchun pul o'tkazadi.

    Bitta buyurtmada bir nechta sotuvchi bo'lishi mumkin — shuning uchun
    sotuvchi bo'yicha guruhlanadi va har biriga bitta tranzaksiya yoziladi.
    """
    totals = (
        OrderItem.objects.filter(order=order, artisan__isnull=False)
        .values("artisan__user")
        .annotate(gross=Sum(F("price") * F("quantity")))
        .values_list("artisan__user", "gross")
    )

    for user_id, gross in totals:
        balance, _ = Balance.objects.get_or_create(user_id=user_id)
        balance.credit(
            gross=gross,
            commission=commission_for(gross),
            type=BalanceTransaction.Type.SALE,
            order=order,
            comment=f"{order.order_number} — sotuvdan tushum",
        )


def _reserve_stock(order: Order) -> None:
    """To'lov tasdiqlangach zaxira kamayadi, tugasa mahsulot `sold` bo'ladi."""
    for item in order.items.select_related("product", "artisan").all():
        product = item.product
        if product is None:
            continue

        product.stock = max(product.stock - item.quantity, 0)
        fields = ["stock", "updated_at"]
        if product.stock == 0 and product.status != Product.Status.SOLD:
            product.status = Product.Status.SOLD
            product.sold_at = timezone.now()
            fields += ["status", "sold_at"]
        product.save(update_fields=fields)

        if item.artisan_id:
            ArtisanProfile.objects.filter(pk=item.artisan_id).update(
                sold_count=F("sold_count") + item.quantity
            )


def _notify_approved(payment: Payment) -> None:
    order = payment.order
    Notification.notify(
        order.user,
        type=Notification.Type.PAYMENT_APPROVED,
        title="To'lov tasdiqlandi",
        body=f"{order.order_number} — {order.total:.0f} so'm. Mahsulot tayyorlanmoqda.",
        link_url="/profil",
    )

    notified = set()
    for item in order.items.select_related("artisan__user").all():
        if not item.artisan_id:
            continue
        user = item.artisan.user
        if user.id in notified:
            continue
        notified.add(user.id)
        Notification.notify(
            user,
            type=Notification.Type.SALE_PAID,
            title="Mahsulotingiz sotildi",
            body=f"{order.order_number} bo'yicha to'lov tasdiqlandi, balansingiz to'ldirildi.",
            link_url="/profil",
        )


def _notify_rejected(payment: Payment) -> None:
    order = payment.order
    body = f"{order.order_number} — chek qabul qilinmadi."
    if payment.reject_reason:
        body += f" Sabab: {payment.reject_reason}"
    Notification.notify(
        order.user,
        type=Notification.Type.PAYMENT_REJECTED,
        title="To'lov rad etildi",
        body=body,
        link_url="/profil",
    )
