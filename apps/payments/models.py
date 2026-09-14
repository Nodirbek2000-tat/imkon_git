"""
To'lov va balans.

To'lov real payment gateway orqali emas — xaridor kartaga pul o'tkazadi va
chek rasmini botga yuboradi. Chek maxfiy Telegram kanaliga tushadi, admin
"Tasdiqlash"/"Rad etish" tugmasini bosadi.

Shuning uchun bu yerda ikki xil "pul" bor va ularni aralashtirmaslik kerak:
  • `Payment` — xaridordan platformaga kelgan (tasdiqlanishi kerak) pul
  • `Balance` — platforma sotuvchiga qarzdor bo'lgan pul (komissiya ayrilgan)
"""

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models, transaction

from apps.common.models import TimeStampedModel
from apps.orders.models import Order


class PaymentCard(TimeStampedModel):
    """
    Pul tushadigan karta. Botda xaridorga shu ko'rsatiladi.

    Karta vaqti-vaqti bilan almashadi (bloklanadi, bank o'zgaradi), lekin
    eski `Payment` yozuvlari qaysi kartaga to'langanini bilib turishi kerak —
    shuning uchun karta o'chirilmaydi, `is_active` o'chiriladi va yangisi
    qo'shiladi.
    """

    number = models.CharField("Karta raqami", max_length=25)
    holder_name = models.CharField("Karta egasi", max_length=100)
    bank = models.CharField("Bank", max_length=60, blank=True)
    note = models.CharField("Qo'shimcha izoh", max_length=200, blank=True)
    is_active = models.BooleanField("Faol", default=True, db_index=True)

    class Meta:
        verbose_name = "To'lov kartasi"
        verbose_name_plural = "To'lov kartalari"
        ordering = ("-is_active", "-created_at")

    def __str__(self):
        return f"{self.number} — {self.holder_name}"

    @classmethod
    def active(cls):
        return cls.objects.filter(is_active=True).first()

    @classmethod
    def make_active(cls, pk: int) -> "PaymentCard":
        """
        Shu kartani yagona faol karta qiladi.

        Bir vaqtda faqat bitta karta faol bo'lishi kerak — bot xaridorga
        aynan bittasini ko'rsatadi. Ikkitasi faol qolib ketsa qaysi biri
        chiqishi tasodifga bog'liq bo'lardi, pul esa boshqa kartaga
        tushib qolishi mumkin edi.

        Shuning uchun yoqish va o'chirish bitta tranzaksiyada.
        """
        with transaction.atomic():
            card = cls.objects.select_for_update().get(pk=pk)
            cls.objects.exclude(pk=pk).filter(is_active=True).update(is_active=False)
            if not card.is_active:
                card.is_active = True
                card.save(update_fields=["is_active", "updated_at"])
            return card


class Payment(TimeStampedModel):
    """
    Bitta to'lov urinishi.

    `Order` bilan FK (OneToOne emas) — chek rad etilsa xaridor qaytadan
    urinib ko'radi va bu yangi yozuv bo'ladi. Bitta buyurtmada bir vaqtda
    faqat bitta "ochiq" (`awaiting_receipt`/`pending`) to'lov bo'lishi
    mumkin — buni `services.start_payment()` ta'minlaydi.
    """

    class Status(models.TextChoices):
        AWAITING_RECEIPT = "awaiting_receipt", "Chek kutilmoqda"
        PENDING = "pending", "Tekshirilmoqda"
        APPROVED = "approved", "Tasdiqlangan"
        REJECTED = "rejected", "Rad etilgan"

    OPEN_STATUSES = (Status.AWAITING_RECEIPT, Status.PENDING)

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="payments")
    card = models.ForeignKey(
        PaymentCard, on_delete=models.SET_NULL, null=True, related_name="payments"
    )

    amount = models.DecimalField(
        "Summa",
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.AWAITING_RECEIPT,
        db_index=True,
    )

    # Chek rasmi Telegram serverida yotadi — `file_id` bilan qayta yuborish
    # mumkin. `receipt_image` esa nusxa: Telegram `file_id`ni bir kun bekor
    # qilsa ham chek Django admin panelida ochiladi.
    receipt_file_id = models.CharField(max_length=200, blank=True)
    receipt_image = models.ImageField(upload_to="receipts/%Y/%m/", blank=True, null=True)
    receipt_sent_at = models.DateTimeField(null=True, blank=True)

    # Maxfiy kanaldagi xabar — tasdiqlangach tugmalarni o'chirish uchun kerak
    channel_message_id = models.BigIntegerField(null=True, blank=True)

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_payments",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reject_reason = models.CharField("Rad etish sababi", max_length=300, blank=True)

    class Meta:
        verbose_name = "To'lov"
        verbose_name_plural = "To'lovlar"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["status", "-created_at"])]

    def __str__(self):
        return f"{self.order.order_number} — {self.amount} ({self.get_status_display()})"

    @property
    def is_open(self) -> bool:
        return self.status in self.OPEN_STATUSES


class Balance(TimeStampedModel):
    """
    Foydalanuvchining platformadagi hisobi.

    Sotuvchida — sotuvdan tushgan (komissiya ayrilgan) pul. Xaridorda
    hozircha ishlatilmaydi, lekin qaytarim (refund) uchun tayyor turadi.

    `amount` ni to'g'ridan-to'g'ri o'zgartirmang — `credit()` ishlating,
    u tranzaksiya tarixini ham yozadi.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="balance"
    )
    amount = models.DecimalField(
        "Balans",
        max_digits=14,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )

    class Meta:
        verbose_name = "Balans"
        verbose_name_plural = "Balanslar"
        ordering = ("-amount",)

    def __str__(self):
        return f"{self.user} — {self.amount}"

    @classmethod
    def for_user(cls, user) -> "Balance":
        balance, _ = cls.objects.get_or_create(user=user)
        return balance

    def credit(
        self,
        *,
        gross: Decimal,
        commission: Decimal,
        type: str = "sale",
        order=None,
        comment: str = "",
    ) -> "BalanceTransaction":
        """
        Balansga pul qo'shadi va tarixga yozadi.

        `select_for_update` — bir sotuvchining ikkita mahsuloti ikki xil
        buyurtmada bir vaqtda tasdiqlanishi mumkin. Qulfsiz ikkalasi ham
        eski `amount` ni o'qib, biri yo'qolib ketardi.
        """
        net = gross - commission
        with transaction.atomic():
            fresh = Balance.objects.select_for_update().get(pk=self.pk)
            fresh.amount += net
            fresh.save(update_fields=["amount", "updated_at"])
            self.amount = fresh.amount

            return BalanceTransaction.objects.create(
                balance=fresh,
                type=type,
                order=order,
                gross_amount=gross,
                commission_amount=commission,
                amount=net,
                balance_after=fresh.amount,
                comment=comment,
            )


class BalanceTransaction(TimeStampedModel):
    """
    Balansdagi har bir harakat. O'chirilmaydi va tahrirlanmaydi —
    sotuvchi "pulim qayerdan keldi" degan savolga javob shu yerda.
    """

    class Type(models.TextChoices):
        SALE = "sale", "Sotuvdan tushum"
        WITHDRAWAL = "withdrawal", "Pul yechish"
        ADJUSTMENT = "adjustment", "Admin tuzatishi"

    balance = models.ForeignKey(
        Balance, on_delete=models.CASCADE, related_name="transactions"
    )
    type = models.CharField(max_length=12, choices=Type.choices, default=Type.SALE)
    order = models.ForeignKey(
        Order, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    # Xaridor to'lagan summa va undan olingan komissiya alohida saqlanadi —
    # "platforma qancha ishladi" degan hisobot shu ustunlardan chiqadi.
    gross_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0")
    )
    commission_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0")
    )
    amount = models.DecimalField("Balansga o'tgan", max_digits=12, decimal_places=2)
    balance_after = models.DecimalField(max_digits=14, decimal_places=2)

    comment = models.CharField(max_length=300, blank=True)

    class Meta:
        verbose_name = "Balans harakati"
        verbose_name_plural = "Balans harakatlari"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["balance", "-created_at"])]

    def __str__(self):
        return f"{self.balance.user_id}: {self.amount}"
