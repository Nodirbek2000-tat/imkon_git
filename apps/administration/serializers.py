from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.accounts.models import User
from apps.artisans.models import ArtisanApplication
from apps.auctions.models import Auction
from apps.catalog.models import Product
from apps.payments.models import PaymentCard


class AdminUserSerializer(serializers.ModelSerializer):
    """Admin ko'radigan foydalanuvchi — telefon raqami bilan."""

    is_admin = serializers.BooleanField(source="is_staff", read_only=True)
    artisan_slug = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id", "phone", "full_name", "avatar", "role",
            "is_admin", "is_active", "is_phone_verified",
            "artisan_slug", "created_at",
        )

    def get_artisan_slug(self, obj) -> str | None:
        profile = getattr(obj, "artisan_profile", None)
        return profile.slug if profile else None


class AdminApplicationSerializer(serializers.ModelSerializer):
    """Kelib tushgan "do'kon ochish" arizasi."""

    user = AdminUserSerializer(read_only=True)
    craft_name = serializers.CharField(source="craft.name_uz", read_only=True)

    class Meta:
        model = ArtisanApplication
        fields = (
            "id", "user", "shop_name", "craft", "craft_name",
            "description", "region", "document",
            "status", "admin_note", "created_at", "reviewed_at",
        )


class ReviewApplicationSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, max_length=1000)


class AdminAuctionSerializer(serializers.ModelSerializer):
    product_title = serializers.CharField(source="product.title_uz", read_only=True)
    artisan_name = serializers.CharField(
        source="product.artisan.shop_name_uz", read_only=True
    )
    winner_name = serializers.SerializerMethodField()
    seconds_left = serializers.IntegerField(read_only=True)

    class Meta:
        model = Auction
        fields = (
            "id", "product_title", "artisan_name",
            "start_price", "current_price", "bids_count",
            "start_at", "end_at", "seconds_left", "status", "winner_name",
        )

    def get_winner_name(self, obj) -> str | None:
        return obj.winner.full_name or obj.winner.phone if obj.winner else None


class AuctionCandidateSerializer(serializers.ModelSerializer):
    """Auksionga qo'yish mumkin bo'lgan mahsulot."""

    artisan_name = serializers.CharField(source="artisan.shop_name_uz", read_only=True)
    image = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ("id", "slug", "title_uz", "price", "artisan_name", "image")
        read_only_fields = fields

    def get_image(self, obj) -> str | None:
        main = next((img for img in obj.images.all() if img.is_main), None)
        image = main or next(iter(obj.images.all()), None)
        return image.image.url if image else None


class AuctionCreateSerializer(serializers.ModelSerializer):
    """
    Admin auksion qo'yadi.

    Mahsulotni hunarmand emas, admin auksionga chiqaradi — shuning uchun
    yaratish paytida mahsulotning `sale_type` va `status` ham to'g'rilanadi.
    Aks holda lot auksionda turib, katalogda oddiy narx bilan sotilaverardi.
    """

    product = serializers.SlugRelatedField(
        slug_field="slug", queryset=Product.objects.all()
    )

    class Meta:
        model = Auction
        fields = ("id", "product", "start_price", "min_increment", "start_at", "end_at")

    def validate_product(self, product):
        if Auction.objects.filter(product=product).exists():
            raise serializers.ValidationError("Bu mahsulot allaqachon auksionda.")
        if product.status == Product.Status.SOLD:
            raise serializers.ValidationError("Sotilgan mahsulotni auksionga qo'yib bo'lmaydi.")
        return product

    def validate(self, attrs):
        start_at, end_at = attrs["start_at"], attrs["end_at"]

        if end_at <= start_at:
            raise serializers.ValidationError(
                {"end_at": "Tugash vaqti boshlanishdan keyin bo'lishi kerak."}
            )
        if end_at <= timezone.now():
            raise serializers.ValidationError(
                {"end_at": "Tugash vaqti o'tib ketgan."}
            )
        return attrs

    def create(self, validated_data):
        product = validated_data["product"]

        # Boshlanish vaqti kelgan bo'lsa darrov jonli — admin ikkinchi marta
        # "boshlash" tugmasini qidirib yurmasin
        validated_data["status"] = (
            Auction.Status.LIVE
            if validated_data["start_at"] <= timezone.now()
            else Auction.Status.PENDING
        )

        with transaction.atomic():
            auction = Auction.objects.create(**validated_data)

            fields = []
            if product.sale_type != Product.SaleType.AUCTION:
                product.sale_type = Product.SaleType.AUCTION
                fields.append("sale_type")
            if product.status == Product.Status.DRAFT:
                product.status = Product.Status.ACTIVE
                fields.append("status")
            if fields:
                product.save(update_fields=fields + ["updated_at"])

        return auction


class AdminPaymentCardSerializer(serializers.ModelSerializer):
    """
    To'lov kartasi — admin panelda ko'rinadi va shu yerdan qo'shiladi.

    `payments_count` — shu kartaga nechta to'lov kelgani. Kartani
    o'chirishdan oldin admin uni ko'rib olishi kerak.
    """

    payments_count = serializers.SerializerMethodField()

    class Meta:
        model = PaymentCard
        fields = (
            "id", "number", "holder_name", "bank", "note",
            "is_active", "payments_count", "created_at",
        )
        read_only_fields = ("id", "is_active", "payments_count", "created_at")

    def get_payments_count(self, obj) -> int:
        return obj.payments.count()

    def validate_number(self, value):
        digits = "".join(ch for ch in value if ch.isdigit())
        if not 16 <= len(digits) <= 19:
            raise serializers.ValidationError(
                "Karta raqami 16–19 raqamdan iborat bo'lishi kerak."
            )
        # Har doim bir xil ko'rinishda saqlaymiz: 8600 1234 5678 9012
        return " ".join(digits[i : i + 4] for i in range(0, len(digits), 4))

    def validate_holder_name(self, value):
        cleaned = " ".join(value.split()).upper()
        if len(cleaned) < 3:
            raise serializers.ValidationError("Ism familiyani to'liq kiriting.")
        return cleaned


class StatsSerializer(serializers.Serializer):
    """Admin panel bosh sahifasidagi raqamlar."""

    users_total = serializers.IntegerField()
    users_new_week = serializers.IntegerField()
    artisans_total = serializers.IntegerField()
    admins_total = serializers.IntegerField()

    applications_pending = serializers.IntegerField()
    applications_total = serializers.IntegerField()

    products_total = serializers.IntegerField()
    products_active = serializers.IntegerField()

    auctions_live = serializers.IntegerField()
    auctions_total = serializers.IntegerField()
    bids_total = serializers.IntegerField()
