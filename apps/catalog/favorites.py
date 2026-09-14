"""Mahsulotni sevimlilarga qo'shish."""

from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel


class Favorite(TimeStampedModel):
    """Foydalanuvchining sevimli mahsuloti."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="favorites"
    )
    product = models.ForeignKey(
        "catalog.Product", on_delete=models.CASCADE, related_name="favorited_by"
    )

    class Meta:
        verbose_name = "Sevimli"
        verbose_name_plural = "Sevimlilar"
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["user", "product"], name="unique_user_product_favorite"
            )
        ]

    def __str__(self):
        return f"{self.user} -> {self.product}"
