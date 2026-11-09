"""
Mahsulotga "layk" bosish.

`Favorite` dan FARQI bor va ikkalasi ham kerak:

  Favorite — foydalanuvchining SHAXSIY ro'yxati ("Sevimlilarim"). Uni
             faqat egasi ko'radi, soni hech qayerda ko'rsatilmaydi.
  Like     — OMMAVIY ovoz. Soni hamma kartada ko'rinadi va "Reyting"
             bo'limi aynan shunga qarab tuziladi.

Shuning uchun sanoq `Product.likes_count` da saqlanadi: reyting
ro'yxati har safar COUNT(*) qilmasligi kerak, ustiga-ustak `with_relations()`
izohlar bilan join qiladi — o'sha joinga yana layk jadvalini qo'shsak
sanoq ko'payib ketardi (bitta layk har bir izoh uchun qayta sanalardi).
Xuddi `ArtisanProfile.products_count` dagidek yondashuv.
"""

from django.conf import settings
from django.db import models
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.common.models import TimeStampedModel


class Like(TimeStampedModel):
    """Foydalanuvchining mahsulotga bergan ovozi."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="likes"
    )
    product = models.ForeignKey(
        "catalog.Product", on_delete=models.CASCADE, related_name="likes"
    )

    class Meta:
        verbose_name = "Layk"
        verbose_name_plural = "Layklar"
        ordering = ("-created_at",)
        constraints = [
            # Bir foydalanuvchi bitta mahsulotga faqat bir marta ovoz beradi
            models.UniqueConstraint(
                fields=["user", "product"], name="unique_user_product_like"
            )
        ]

    def __str__(self):
        return f"{self.user} ♥ {self.product}"


@receiver([post_save, post_delete], sender=Like)
def _sync_likes_count(sender, instance, **kwargs):
    """
    `Product.likes_count` ni haqiqiy son bilan tenglashtiradi.

    `F("likes_count") + 1` emas, to'liq COUNT: signal o'tkazib yuborilgan
    holat (admin paneldan ommaviy o'chirish, `loaddata`) sanoqni abadiy
    noto'g'ri qoldirardi. Layk bosish kam uchraydigan amal, bitta COUNT
    arzon.
    """
    from .models import Product

    Product.objects.filter(pk=instance.product_id).update(
        likes_count=Like.objects.filter(product_id=instance.product_id).count()
    )
