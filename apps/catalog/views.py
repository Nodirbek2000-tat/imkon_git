from django.db.models import Count, F, Prefetch, Q, Sum
from django.utils import timezone
from django_filters import rest_framework as filters
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.common.permissions import IsArtisan, IsOwnerOrReadOnly
from apps.notifications.models import Notification

from .favorites import Favorite
from .models import Category, Comment, Product
from .serializers import (
    CategorySerializer,
    CommentCreateSerializer,
    CommentSerializer,
    ProductDetailSerializer,
    ProductListSerializer,
    ProductWriteSerializer,
)


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = (AllowAny,)
    lookup_field = "slug"
    pagination_class = None  # kategoriyalar kam — bir marta yuklanadi


class ProductFilter(filters.FilterSet):
    category = filters.CharFilter(field_name="category__slug")
    artisan = filters.CharFilter(field_name="artisan__slug")
    min_price = filters.NumberFilter(field_name="price", lookup_expr="gte")
    max_price = filters.NumberFilter(field_name="price", lookup_expr="lte")
    region = filters.CharFilter(field_name="artisan__region", lookup_expr="iexact")

    class Meta:
        model = Product
        fields = ("category", "artisan", "sale_type", "min_price", "max_price", "region")


class ProductViewSet(viewsets.ModelViewSet):
    """
    Ommaviy o'qish + hunarmand uchun yozish.

    GET  /api/products/           — katalog
    GET  /api/products/{slug}/    — mahsulot sahifasi
    POST /api/products/           — faqat hunarmand
    """

    lookup_field = "slug"
    filterset_class = ProductFilter
    search_fields = ("title_uz", "title_ru", "title_en", "artisan__shop_name_uz")
    ordering_fields = ("price", "created_at", "views_count")
    ordering = ("-created_at",)

    def get_queryset(self):
        base = Product.objects.with_relations().with_favorited(self.request.user)

        # Mahsulot sahifasida auksion va xususiyatlar ham kerak
        if self.action == "retrieve":
            base = base.select_related("auction").prefetch_related("features")

        # Hunarmand o'z qoralamalarini ham ko'radi
        if self.request.user.is_authenticated and getattr(self.request.user, "is_artisan", False):
            if self.request.query_params.get("mine") == "1":
                return base.filter(artisan__user=self.request.user)

        return base.published()

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return ProductWriteSerializer
        if self.action == "retrieve":
            return ProductDetailSerializer
        return ProductListSerializer

    def get_permissions(self):
        # Izohlar hammaga ochiq (POST ichida login tekshiriladi),
        # o'chirish esa login talab qiladi
        if self.action in ("list", "retrieve", "comments"):
            return [AllowAny()]
        if self.action == "delete_comment":
            return [IsAuthenticated()]
        if self.action in ("my_written_comments", "favorite", "my_favorites"):
            return [IsAuthenticated()]
        if self.action in ("create", "my_comments", "my_stats"):
            return [IsArtisan()]
        return [IsArtisan(), IsOwnerOrReadOnly()]

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        # F() bilan — o'qib-yozish o'rniga bitta UPDATE, race condition yo'q
        Product.objects.filter(slug=kwargs["slug"]).update(views_count=F("views_count") + 1)
        return response

    # ------------------------------------------------------------ izohlar

    @action(detail=True, methods=["get", "post"], permission_classes=[AllowAny])
    def comments(self, request, slug=None):
        """
        GET  — izohlar (javoblari bilan)
        POST — yangi izoh (login kerak)
        """
        product = self.get_object()

        if request.method == "POST":
            if not request.user.is_authenticated:
                return Response(
                    {"detail": "Izoh qoldirish uchun kiring."},
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            serializer = CommentCreateSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            comment = serializer.save(product=product, user=request.user)

            # Mahsulot egasiga xabar — o'zi o'ziga izoh yozsa yubormaymiz
            owner = product.artisan.user
            if owner.id != request.user.id:
                author = request.user.full_name or "Kimdir"
                Notification.notify(
                    owner,
                    type=Notification.Type.NEW_COMMENT,
                    title=f"“{product.title_uz}” ga yangi izoh",
                    body=f"{author}: {comment.text[:200]}",
                    link_url=f"/mahsulot/{product.slug}",
                )

            return Response(
                CommentSerializer(comment, context={"request": request}).data,
                status=status.HTTP_201_CREATED,
            )

        # Javoblarni bitta so'rovda oldindan yuklaymiz — N+1 bo'lmasin
        replies = Comment.objects.filter(is_hidden=False).select_related("user").order_by(
            "created_at"
        )
        top_level = (
            Comment.objects.filter(product=product, parent__isnull=True, is_hidden=False)
            .select_related("user")
            .prefetch_related(Prefetch("replies", queryset=replies, to_attr="prefetched_replies"))
            .order_by("-created_at")
        )

        page = self.paginate_queryset(top_level)
        serializer = CommentSerializer(page, many=True, context={"request": request})
        return self.get_paginated_response(serializer.data)

    # ------------------------------------------------------------ sevimlilar

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def favorite(self, request, slug=None):
        """Sevimlilarga qo'shish/olib tashlash — bir so'rovda ikkalasi ham."""
        product = self.get_object()
        favorite, created = Favorite.objects.get_or_create(user=request.user, product=product)
        if not created:
            favorite.delete()
        return Response({"favorited": created})

    @action(detail=False, methods=["get"], url_path="my-favorites")
    def my_favorites(self, request):
        """O'zi saqlab qo'ygan mahsulotlar — "Sevimlilarim" bo'limi."""
        # `id__in` bilan filtrlaymiz, `favorited_by` orqali join emas —
        # aks holda `with_relations()`dagi reyting annotatsiyasi ikki marta
        # join bo'lib, noto'g'ri (shishirilgan) qiymat berardi
        favorite_ids = Favorite.objects.filter(user=request.user).values_list(
            "product_id", flat=True
        )
        products = (
            Product.objects.with_relations()
            .with_favorited(request.user)
            .filter(id__in=list(favorite_ids))
        )
        page = self.paginate_queryset(products)
        serializer = ProductListSerializer(page, many=True, context={"request": request})
        return self.get_paginated_response(serializer.data)

    @action(
        detail=True,
        methods=["delete"],
        url_path="comments/(?P<comment_id>[^/.]+)",
        permission_classes=[IsAuthenticated],
    )
    def delete_comment(self, request, slug=None, comment_id=None):
        """O'z izohini o'chirish (admin har qanday izohni o'chira oladi)."""
        try:
            comment = Comment.objects.get(pk=comment_id, product__slug=slug)
        except Comment.DoesNotExist:
            return Response({"detail": "Izoh topilmadi."}, status=status.HTTP_404_NOT_FOUND)

        if comment.user_id != request.user.id and not request.user.is_staff:
            return Response(
                {"detail": "Bu izohni o'chira olmaysiz."}, status=status.HTTP_403_FORBIDDEN
            )

        comment.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    # ------------------------------------------------------------ "mening"

    @action(detail=False, methods=["get"], url_path="my-comments")
    def my_comments(self, request):
        """O'z mahsulotlariga yozilgan barcha izohlar — bitta ro'yxatda."""
        artisan = getattr(request.user, "artisan_profile", None)
        comments = (
            Comment.objects.filter(product__artisan=artisan, is_hidden=False)
            .select_related("product", "user")
            .order_by("-created_at")
            if artisan is not None
            else Comment.objects.none()
        )
        page = self.paginate_queryset(comments)
        serializer = CommentSerializer(page, many=True, context={"request": request})
        return self.get_paginated_response(serializer.data)

    @action(detail=False, methods=["get"], url_path="my-written-comments")
    def my_written_comments(self, request):
        """O'zi yozgan barcha sharhlar — "Sharhlarim" bo'limi, hamma foydalanuvchi uchun."""
        comments = (
            Comment.objects.filter(user=request.user, is_hidden=False)
            .select_related("product")
            .prefetch_related("product__images")
            .order_by("-created_at")
        )
        page = self.paginate_queryset(comments)
        serializer = CommentSerializer(page, many=True, context={"request": request})
        return self.get_paginated_response(serializer.data)

    @action(detail=False, methods=["get"], url_path="my-stats")
    def my_stats(self, request):
        """Sotuvchi statistikasi — mahsulotlar soni, sotilgan, daromad."""
        artisan = getattr(request.user, "artisan_profile", None)
        empty = {
            "products_total": 0, "products_active": 0, "products_sold": 0,
            "revenue_total": 0, "sold_this_month": 0, "revenue_this_month": 0,
        }
        if artisan is None:
            return Response(empty)

        month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        stats = Product.objects.filter(artisan=artisan).aggregate(
            products_total=Count("id"),
            products_active=Count("id", filter=Q(status=Product.Status.ACTIVE)),
            products_sold=Count("id", filter=Q(status=Product.Status.SOLD)),
            revenue_total=Sum("price", filter=Q(status=Product.Status.SOLD)),
            sold_this_month=Count(
                "id", filter=Q(status=Product.Status.SOLD, sold_at__gte=month_start)
            ),
            revenue_this_month=Sum(
                "price", filter=Q(status=Product.Status.SOLD, sold_at__gte=month_start)
            ),
        )
        stats["revenue_total"] = stats["revenue_total"] or 0
        stats["revenue_this_month"] = stats["revenue_this_month"] or 0
        return Response(stats)
