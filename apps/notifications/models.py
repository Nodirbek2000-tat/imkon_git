from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel


class Notification(TimeStampedModel):
    """
    Ichki bildirishnoma — profildagi "Bildirishnomalar" ro'yxati.

    `link_url` oddiy matn (GenericForeignKey emas) — trigger nuqtalari o'z
    URL'ini biladi, murakkab bog'lanish shart emas. Mahsulot o'chirilsa
    havola o'lik qolishi mumkin — frontend buni yumshoq ushlaydi.
    """

    class Type(models.TextChoices):
        APPLICATION_APPROVED = "application_approved", "Ariza tasdiqlandi"
        APPLICATION_REJECTED = "application_rejected", "Ariza rad etildi"
        NEW_COMMENT = "new_comment", "Yangi izoh"
        ORDER_PLACED = "order_placed", "Buyurtma qabul qilindi"
        NEW_ORDER = "new_order", "Yangi buyurtma"
        PAYMENT_APPROVED = "payment_approved", "To'lov tasdiqlandi"
        PAYMENT_REJECTED = "payment_rejected", "To'lov rad etildi"
        SALE_PAID = "sale_paid", "Mahsulot sotildi"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    type = models.CharField(max_length=30, choices=Type.choices)
    title = models.CharField(max_length=140)
    body = models.TextField(max_length=1000, blank=True)
    link_url = models.CharField(max_length=300, blank=True)
    is_read = models.BooleanField(default=False, db_index=True)

    class Meta:
        verbose_name = "Bildirishnoma"
        verbose_name_plural = "Bildirishnomalar"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["user", "is_read", "-created_at"])]

    def __str__(self):
        return f"{self.user_id} — {self.title}"

    @classmethod
    def notify(cls, user, *, type, title, body="", link_url=""):
        """Trigger nuqtalari uchun qisqa yordamchi."""
        return cls.objects.create(
            user=user, type=type, title=title, body=body, link_url=link_url
        )
