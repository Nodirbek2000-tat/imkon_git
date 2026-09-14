"""Savat va buyurtma.

To'lov `apps.payments` da: xaridor Telegram bot orqali kartaga o'tkazadi va
chek yuboradi, admin tasdiqlaganda `Order.status` `paid` bo'ladi. Yetkazib
berish bosqichlari (`shipped`, `delivered`) hali yo'q.
"""

import secrets
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from apps.artisans.models import ArtisanProfile
from apps.catalog.models import Product
from apps.common.models import TimeStampedModel


class CartItem(TimeStampedModel):
    """Foydalanuvchi savatidagi bitta mahsulot."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cart_items"
    )
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="+")
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])

    class Meta:
        verbose_name = "Savat elementi"
        verbose_name_plural = "Savat elementlari"
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["user", "product"], name="unique_user_product_cart_item"
            )
        ]

    def __str__(self):
        return f"{self.user} — {self.product} x{self.quantity}"


def _generate_order_number() -> str:
    return f"IM-{secrets.token_hex(4).upper()}"


class Order(TimeStampedModel):
    """Xaridorning buyurtmasi."""

    class Status(models.TextChoices):
        PENDING = "pending", "To'lov kutilmoqda"
        PAID = "paid", "To'lov qilindi"
        CANCELLED = "cancelled", "Bekor qilindi"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="orders"
    )
    order_number = models.CharField(
        max_length=20, unique=True, default=_generate_order_number, editable=False
    )

    full_name = models.CharField("Qabul qiluvchi", max_length=120)
    phone = models.CharField("Telefon", max_length=13)
    address = models.TextField("Manzil", max_length=500)

    total = models.DecimalField(
        "Jami summa",
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True
    )

    class Meta:
        verbose_name = "Buyurtma"
        verbose_name_plural = "Buyurtmalar"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["user", "-created_at"])]

    def __str__(self):
        return self.order_number


class OrderItem(models.Model):
    """
    Buyurtma tarkibidagi bitta mahsulot.

    Narx va nom shu yerda "suratga olinadi" — sotuvchi keyin narxni
    o'zgartirsa yoki mahsulotni o'chirsa ham, eski buyurtma tarixi
    o'zgarmay qoladi.
    """

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        Product, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    artisan = models.ForeignKey(
        ArtisanProfile, on_delete=models.SET_NULL, null=True, related_name="order_items"
    )

    title = models.CharField(max_length=140)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = "Buyurtma tarkibi"
        verbose_name_plural = "Buyurtma tarkibi"

    def __str__(self):
        return f"{self.title} x{self.quantity}"

    @property
    def subtotal(self):
        return self.price * self.quantity
