from decimal import Decimal

from rest_framework import serializers

from apps.catalog.serializers import ProductDetailSerializer, ProductListSerializer

from .models import Auction, Bid


class BidSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = Bid
        fields = ("id", "amount", "user_name", "created_at")

    def get_user_name(self, obj) -> str:
        """
        Taklif tarixida to'liq ism ko'rsatilmaydi.
        "Dilnoza K." — kim taklif qilgani bilinadi, maxfiylik saqlanadi.
        """
        name = obj.user.full_name.strip()
        if not name:
            return f"***{obj.user.phone[-4:]}"

        parts = name.split()
        return f"{parts[0]} {parts[1][0]}." if len(parts) > 1 else parts[0]


class AuctionListSerializer(serializers.ModelSerializer):
    product = ProductListSerializer(read_only=True)
    next_min_bid = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    seconds_left = serializers.IntegerField(read_only=True)
    is_live = serializers.BooleanField(read_only=True)

    class Meta:
        model = Auction
        fields = (
            "id", "product", "start_price", "current_price", "min_increment",
            "next_min_bid", "start_at", "end_at", "seconds_left",
            "status", "is_live", "bids_count",
        )


class AuctionDetailSerializer(AuctionListSerializer):
    """
    Lot sahifasi.

    `product` bu yerda TO'LIQ (ro'yxatdagi qisqartirilgani emas): xaridor
    narx taklif qilishdan oldin nimaga pul tikayotganini ko'rishi kerak —
    barcha rasmlar, tavsif va xususiyatlar bilan.
    """

    product = ProductDetailSerializer(read_only=True)
    bids = serializers.SerializerMethodField()
    my_max_bid = serializers.SerializerMethodField()

    class Meta(AuctionListSerializer.Meta):
        fields = AuctionListSerializer.Meta.fields + ("bids", "my_max_bid", "winner")

    def get_bids(self, obj) -> list:
        # Oxirgi 20 ta taklif — butun tarixni yuklash sahifani sekinlashtiradi
        recent = obj.bids.select_related("user").order_by("-amount")[:20]
        return BidSerializer(recent, many=True, context=self.context).data

    def get_my_max_bid(self, obj) -> Decimal | None:
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return None
        top = obj.bids.filter(user=request.user).order_by("-amount").first()
        return top.amount if top else None


class PlaceBidSerializer(serializers.Serializer):
    """
    Taklif qo'yish.

    Foydalanuvchi to'liq summani yuboradi (masalan 420000), yoki
    `increment=true` bilan joriy narxga minimal qadam qo'shiladi.
    """

    amount = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    increment = serializers.BooleanField(default=False)

    def validate(self, attrs):
        if not attrs.get("increment") and attrs.get("amount") is None:
            raise serializers.ValidationError(
                "`amount` yuboring yoki `increment: true` qiling."
            )
        return attrs
