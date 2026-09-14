from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.utils import timezone

from apps.catalog.models import Product
from apps.common.models import TimeStampedModel

# Oxirgi daqiqalarda taklif kelsa auksion cho'ziladi — "sniping" ga qarshi
ANTI_SNIPE_WINDOW = timedelta(minutes=2)
ANTI_SNIPE_EXTENSION = timedelta(minutes=2)


class BidError(ValidationError):
    """Taklif qabul qilinmadi — sabab foydalanuvchiga ko'rsatiladi."""


class AuctionQuerySet(models.QuerySet):
    def live(self):
        now = timezone.now()
        return self.filter(status=Auction.Status.LIVE, start_at__lte=now, end_at__gt=now)

    def with_relations(self):
        # `product__features` lot sahifasi uchun — u mahsulotni to'liq
        # ko'rsatadi. Ro'yxatga ortiqcha, lekin bitta qo'shimcha so'rov
        # ikkita alohida queryset saqlashdan arzonroq.
        return self.select_related(
            "product", "product__artisan", "product__category", "winner"
        ).prefetch_related("product__images", "product__features")


class Auction(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Boshlanmagan"
        LIVE = "live", "Jonli"
        ENDED = "ended", "Tugagan"
        CANCELLED = "cancelled", "Bekor qilingan"

    product = models.OneToOneField(
        Product, on_delete=models.CASCADE, related_name="auction"
    )

    start_price = models.DecimalField(
        "Boshlang'ich narx", max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    current_price = models.DecimalField(
        "Joriy narx", max_digits=12, decimal_places=2, editable=False
    )
    min_increment = models.DecimalField(
        "Minimal qadam", max_digits=12, decimal_places=2, default=Decimal("5000.00"),
        validators=[MinValueValidator(Decimal("100.00"))],
    )

    start_at = models.DateTimeField(db_index=True)
    end_at = models.DateTimeField(db_index=True)

    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    winner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="won_auctions",
    )
    bids_count = models.PositiveIntegerField(default=0, editable=False)

    objects = AuctionQuerySet.as_manager()

    class Meta:
        verbose_name = "Auksion"
        verbose_name_plural = "Auksionlar"
        ordering = ("end_at",)
        indexes = [models.Index(fields=["status", "end_at"])]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_at__gt=models.F("start_at")),
                name="auction_ends_after_start",
            )
        ]

    def __str__(self):
        return f"{self.product.title_uz} — {self.current_price} so'm"

    def save(self, *args, **kwargs):
        if self._state.adding and not self.current_price:
            self.current_price = self.start_price
        super().save(*args, **kwargs)

    # ------------------------------------------------------------ holat

    @property
    def is_live(self) -> bool:
        now = timezone.now()
        return self.status == self.Status.LIVE and self.start_at <= now < self.end_at

    @property
    def next_min_bid(self) -> Decimal:
        """Foydalanuvchi kamida shu summani taklif qilishi kerak."""
        if self.bids_count == 0:
            return self.start_price
        return self.current_price + self.min_increment

    @property
    def seconds_left(self) -> int:
        return max(int((self.end_at - timezone.now()).total_seconds()), 0)

    # ------------------------------------------------------------ taklif

    @classmethod
    def place_bid(cls, auction_id: int, user, amount: Decimal) -> "Bid":
        """
        Taklif qo'yish.

        `select_for_update` — bu yerdagi eng muhim qator. Ikki kishi bir
        vaqtda taklif qilsa, ikkalasi ham eski `current_price` ni o'qib,
        ikkalasi ham yutgan bo'lib qolardi. Qulf birinchisini o'tkazadi,
        ikkinchisi yangilangan narxni ko'radi va rad etiladi.

        SQLite bu qulfni to'liq qo'llamaydi — production'da PostgreSQL kerak.
        """
        with transaction.atomic():
            auction = (
                cls.objects.select_for_update()
                .select_related("product__artisan__user")
                .get(pk=auction_id)
            )

            if not auction.is_live:
                raise BidError("Auksion faol emas.")

            if auction.product.artisan.user_id == user.id:
                raise BidError("O'z lotingizga taklif qila olmaysiz.")

            last_bid = auction.bids.order_by("-amount").first()
            if last_bid and last_bid.user_id == user.id:
                raise BidError("Siz allaqachon eng yuqori taklifni qo'ygansiz.")

            if amount < auction.next_min_bid:
                raise BidError(
                    f"Kamida {auction.next_min_bid:.0f} so'm taklif qilishingiz kerak."
                )

            bid = Bid.objects.create(auction=auction, user=user, amount=amount)

            auction.current_price = amount
            auction.bids_count += 1

            # Anti-sniping: tugashiga oz qolganda taklif kelsa vaqt cho'ziladi
            if auction.end_at - timezone.now() < ANTI_SNIPE_WINDOW:
                auction.end_at += ANTI_SNIPE_EXTENSION
                auction.save(update_fields=["current_price", "bids_count", "end_at", "updated_at"])
            else:
                auction.save(update_fields=["current_price", "bids_count", "updated_at"])

            return bid

    def finalize(self):
        """Vaqti tugagan auksionni yakunlaydi va g'olibni belgilaydi."""
        if self.status != self.Status.LIVE or timezone.now() < self.end_at:
            return

        top = self.bids.order_by("-amount", "created_at").first()
        self.status = self.Status.ENDED
        self.winner = top.user if top else None
        self.save(update_fields=["status", "winner", "updated_at"])

        if top:
            Product.objects.filter(pk=self.product_id).update(status=Product.Status.SOLD)


class Bid(TimeStampedModel):
    auction = models.ForeignKey(Auction, on_delete=models.CASCADE, related_name="bids")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bids"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        verbose_name = "Taklif"
        verbose_name_plural = "Takliflar"
        ordering = ("-amount", "-created_at")
        indexes = [models.Index(fields=["auction", "-amount"])]
        constraints = [
            # Bitta auksionda bir xil summa ikki marta bo'lmaydi —
            # qulf ishlamay qolgan holatda ham baza himoya qiladi
            models.UniqueConstraint(
                fields=["auction", "amount"], name="unique_amount_per_auction"
            )
        ]

    def __str__(self):
        return f"{self.user.phone} — {self.amount} so'm"
