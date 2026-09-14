from rest_framework import serializers

from apps.catalog.models import Product
from apps.catalog.serializers import ProductListSerializer

from .models import CartItem, Order, OrderItem


class CartItemSerializer(serializers.ModelSerializer):
    product = ProductListSerializer(read_only=True)
    subtotal = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = ("id", "product", "quantity", "subtotal", "created_at")
        read_only_fields = fields

    def get_subtotal(self, obj) -> str:
        return str(obj.product.price * obj.quantity)


class CartItemCreateSerializer(serializers.Serializer):
    product = serializers.SlugRelatedField(
        slug_field="slug", queryset=Product.objects.published()
    )
    quantity = serializers.IntegerField(min_value=1, default=1)


class CartItemUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CartItem
        fields = ("quantity",)


class OrderItemSerializer(serializers.ModelSerializer):
    product_slug = serializers.SerializerMethodField()
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = OrderItem
        fields = ("id", "title", "price", "quantity", "subtotal", "product_slug")

    def get_product_slug(self, obj) -> str | None:
        return obj.product.slug if obj.product else None


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    payment_status = serializers.SerializerMethodField()
    reject_reason = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            "id", "order_number", "full_name", "phone", "address",
            "total", "status", "payment_status", "reject_reason",
            "items", "created_at",
        )
        read_only_fields = fields

    def _last_payment(self, obj):
        # `payments` odatda prefetch qilingan — qayta so'rov ketmasligi uchun
        # tartiblashni Python tomonida qilamiz (`Meta.ordering` yangisi birinchi)
        payments = list(obj.payments.all())
        return payments[0] if payments else None

    def get_payment_status(self, obj) -> str | None:
        """
        Saytda buyurtma yonida ko'rinadigan to'lov holati.

        `Order.status` yetarli emas: to'lanmagan buyurtma "chek yuborilmagan"
        ham, "chek tekshirilmoqda" ham bo'lishi mumkin — foydalanuvchi uchun
        bu ikkisi butunlay boshqa narsa.
        """
        payment = self._last_payment(obj)
        return payment.status if payment else None

    def get_reject_reason(self, obj) -> str:
        payment = self._last_payment(obj)
        return payment.reject_reason if payment else ""


class CheckoutSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=120)
    phone = serializers.CharField(max_length=13)
    address = serializers.CharField(max_length=500)
