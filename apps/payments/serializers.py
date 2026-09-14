from rest_framework import serializers

from apps.orders.models import Order

from .models import Balance, BalanceTransaction, Payment, PaymentCard


class PaymentCardSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentCard
        fields = ("id", "number", "holder_name", "bank", "note")
        read_only_fields = fields


class PaymentSerializer(serializers.ModelSerializer):
    """Saytda buyurtma yonida ko'rsatiladigan qisqa holat."""

    card = PaymentCardSerializer(read_only=True)

    class Meta:
        model = Payment
        fields = (
            "id", "amount", "status", "card",
            "reject_reason", "receipt_sent_at", "reviewed_at", "created_at",
        )
        read_only_fields = fields


# ------------------------------------------------------------------ bot


class BotOrderItemSerializer(serializers.Serializer):
    title = serializers.CharField()
    price = serializers.DecimalField(max_digits=12, decimal_places=2)
    quantity = serializers.IntegerField()
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2)


class BotOrderSerializer(serializers.ModelSerializer):
    """
    Bot xaridorga ko'rsatadigan buyurtma.

    `OrderSerializer`dan ajratilgan — botga sayt havolalari yoki
    `product_slug` kerak emas, lekin ochiq to'lov holati kerak.
    """

    items = BotOrderItemSerializer(many=True, read_only=True)
    payment = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            "id", "order_number", "full_name", "phone", "address",
            "total", "status", "items", "payment", "created_at",
        )
        read_only_fields = fields

    def get_payment(self, obj) -> dict | None:
        payment = next(
            (p for p in obj.payments.all() if p.is_open),
            None,
        )
        return PaymentSerializer(payment).data if payment else None


class BotUserSyncSerializer(serializers.Serializer):
    """Bot `/start` da yuboradigan ma'lumot."""

    telegram_id = serializers.IntegerField()
    telegram_username = serializers.CharField(max_length=64, allow_blank=True, default="")
    full_name = serializers.CharField(max_length=120, allow_blank=True, default="")
    phone = serializers.RegexField(r"^\+998\d{9}$")


class ReceiptSerializer(serializers.Serializer):
    file_id = serializers.CharField(max_length=200)


class ChannelMessageSerializer(serializers.Serializer):
    message_id = serializers.IntegerField()


class ReviewSerializer(serializers.Serializer):
    """Kanaldagi tugma bosilganda keladi."""

    admin_telegram_id = serializers.IntegerField()
    reason = serializers.CharField(max_length=300, allow_blank=True, default="")


# ------------------------------------------------------------------ balans


class BalanceTransactionSerializer(serializers.ModelSerializer):
    order_number = serializers.CharField(source="order.order_number", default=None)
    type_display = serializers.CharField(source="get_type_display", read_only=True)

    class Meta:
        model = BalanceTransaction
        fields = (
            "id", "type", "type_display", "order_number",
            "gross_amount", "commission_amount", "amount", "balance_after",
            "comment", "created_at",
        )
        read_only_fields = fields


class BalanceSerializer(serializers.ModelSerializer):
    commission_percent = serializers.SerializerMethodField()

    class Meta:
        model = Balance
        fields = ("amount", "commission_percent", "updated_at")
        read_only_fields = fields

    def get_commission_percent(self, obj) -> float:
        from django.conf import settings

        return float(settings.PLATFORM_COMMISSION_PERCENT)
