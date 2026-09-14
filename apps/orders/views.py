from decimal import Decimal

from django.db import transaction
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.notifications.models import Notification

from .models import CartItem, Order, OrderItem
from .serializers import (
    CartItemCreateSerializer,
    CartItemSerializer,
    CartItemUpdateSerializer,
    CheckoutSerializer,
    OrderSerializer,
)


class CartViewSet(viewsets.ModelViewSet):
    """
    O'z savati.

    Har bir foydalanuvchi faqat o'z `CartItem`larini ko'radi/o'zgartiradi —
    `get_queryset()` shu bilan cheklaydi, alohida ruxsat tekshiruvi kerak
    emas (topilmasa `get_object()` 404 qaytaradi, boshqa birovnikini
    ko'rsatib qo'ymaydi).
    """

    permission_classes = (IsAuthenticated,)
    pagination_class = None  # savat odatda kichik — sahifalash ortiqcha

    def get_queryset(self):
        return (
            CartItem.objects.filter(user=self.request.user)
            .select_related("product", "product__artisan", "product__category")
            .prefetch_related("product__images")
        )

    def get_serializer_class(self):
        if self.action == "create":
            return CartItemCreateSerializer
        if self.action == "partial_update":
            return CartItemUpdateSerializer
        return CartItemSerializer

    def create(self, request, *args, **kwargs):
        serializer = CartItemCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = serializer.validated_data["product"]
        quantity = serializer.validated_data["quantity"]

        # Mahsulot allaqachon savatda bo'lsa — sonini qo'shamiz,
        # dublikat qator (unique constraint) yaratmaymiz
        item, created = CartItem.objects.get_or_create(
            user=request.user, product=product, defaults={"quantity": quantity}
        )
        if not created:
            item.quantity += quantity
            item.save(update_fields=["quantity", "updated_at"])

        return Response(
            CartItemSerializer(item, context={"request": request}).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def partial_update(self, request, *args, **kwargs):
        item = self.get_object()
        serializer = CartItemUpdateSerializer(item, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(CartItemSerializer(item, context={"request": request}).data)


class OrderViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """
    "Buyurtmalarim". To'lov hali ulanmagan — checkout buyurtmani
    `pending` holatda yaratadi va savatni bo'shatadi.
    """

    permission_classes = (IsAuthenticated,)
    serializer_class = OrderSerializer

    def get_queryset(self):
        return (
            Order.objects.filter(user=self.request.user)
            .prefetch_related("items", "payments")
        )

    def create(self, request, *args, **kwargs):
        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        cart_items = list(
            CartItem.objects.filter(user=request.user).select_related(
                "product", "product__artisan"
            )
        )
        if not cart_items:
            return Response({"detail": "Savat bo'sh."}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            total = sum(
                (item.product.price * item.quantity for item in cart_items), Decimal("0")
            )
            order = Order.objects.create(
                user=request.user, total=total, **serializer.validated_data
            )
            OrderItem.objects.bulk_create(
                OrderItem(
                    order=order,
                    product=item.product,
                    artisan=item.product.artisan,
                    title=item.product.title_uz,
                    price=item.product.price,
                    quantity=item.quantity,
                )
                for item in cart_items
            )
            CartItem.objects.filter(user=request.user).delete()

        self._notify(request.user, order, cart_items)

        return Response(
            OrderSerializer(order, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    @staticmethod
    def _notify(buyer, order, cart_items):
        Notification.notify(
            buyer,
            type=Notification.Type.ORDER_PLACED,
            title="Buyurtmangiz qabul qilindi",
            body=f"{order.order_number} — {len(cart_items)} ta mahsulot.",
            link_url="/profil",
        )

        # Har bir sotuvchiga alohida — bitta buyurtmada bir nechta
        # sotuvchidan xarid qilingan bo'lishi mumkin
        notified = {buyer.id}
        for item in cart_items:
            artisan_user = item.product.artisan.user
            if artisan_user.id in notified:
                continue
            notified.add(artisan_user.id)
            Notification.notify(
                artisan_user,
                type=Notification.Type.NEW_ORDER,
                title="Yangi buyurtma tushdi",
                body=f"{order.order_number} raqamli buyurtmada mahsulotingiz bor.",
                link_url="/profil",
            )

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        order = self.get_object()
        if order.status != Order.Status.PENDING:
            return Response(
                {"detail": "Faqat to'lov kutilayotgan buyurtmani bekor qilish mumkin."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        order.status = Order.Status.CANCELLED
        order.save(update_fields=["status", "updated_at"])
        return Response(OrderSerializer(order, context={"request": request}).data)
