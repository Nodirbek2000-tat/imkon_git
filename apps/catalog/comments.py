"""Mahsulotga izoh qoldirish."""

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.common.models import TimeStampedModel


class Comment(TimeStampedModel):
    """
    Mahsulot ostidagi izoh.

    Bir pog'onali javob qo'llanadi (`parent`) — cheksiz ichma-ich emas.
    Chuqur daraxt UI'da o'qishni qiyinlashtiradi va so'rovni og'irlashtiradi.
    """

    product = models.ForeignKey(
        "catalog.Product", on_delete=models.CASCADE, related_name="comments"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="comments"
    )
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="replies"
    )

    text = models.TextField("Izoh", max_length=1500)
    is_hidden = models.BooleanField("Yashirilgan", default=False, db_index=True)

    # Faqat asosiy (parent=None) izohlarga ma'noli — mahsulotga baho.
    # Javoblarga (reply) reyting so'ralmaydi, shuning uchun cheklanmagan
    # (null qoladi), lekin serializer darajasida yozilmasligi ta'minlanadi.
    rating = models.PositiveSmallIntegerField(
        "Baho",
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )

    class Meta:
        verbose_name = "Izoh"
        verbose_name_plural = "Izohlar"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["product", "is_hidden", "-created_at"])]

    def __str__(self):
        return f"{self.user.full_name or self.user.phone}: {self.text[:40]}"
