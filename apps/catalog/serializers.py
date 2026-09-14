from django.utils import timezone
from rest_framework import serializers

from apps.common.translation import TranslatedSerializerMixin

from .models import Category, Comment, Product, ProductFeature, ProductImage


class CategorySerializer(TranslatedSerializerMixin, serializers.ModelSerializer):
    translated_fields = ("name",)

    class Meta:
        model = Category
        fields = ("id", "slug", "name_uz", "name_ru", "name_en", "icon", "parent")


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ("id", "image", "alt_text", "is_main", "order")


class ArtisanBriefSerializer(serializers.Serializer):
    """Mahsulot kartasida ko'rinadigan qisqa hunarmand ma'lumoti."""

    id = serializers.IntegerField()
    slug = serializers.CharField()
    shop_name = serializers.SerializerMethodField()
    region = serializers.CharField()

    def get_shop_name(self, obj) -> str:
        from apps.common.translation import resolve_language

        return obj.tr("shop_name", resolve_language(self.context.get("request")))


class ProductListSerializer(TranslatedSerializerMixin, serializers.ModelSerializer):
    """Katalog ro'yxati — yengil, faqat kerakli maydonlar."""

    translated_fields = ("title",)

    artisan = ArtisanBriefSerializer(read_only=True)
    category = CategorySerializer(read_only=True)
    main_image = serializers.SerializerMethodField()
    # Katalog kartasi ustiga sichqoncha kelganda rasmlar almashadi — shuning
    # uchun ro'yxatda ham barcha rasmlar kerak. `with_relations()` ularni
    # prefetch qilgan, qo'shimcha so'rov ketmaydi.
    gallery = serializers.SerializerMethodField()
    has_auction = serializers.SerializerMethodField()
    # `ProductViewSet.get_queryset()` annotatsiya qiladi — bu yerda hisoblanmaydi.
    # Baho yo'q bo'lsa `rating_avg` `None` bo'ladi, frontend hech narsa ko'rsatmaydi.
    rating_avg = serializers.FloatField(read_only=True, default=None)
    rating_count = serializers.IntegerField(read_only=True, default=0)
    # `with_favorited()` annotatsiya qiladi — bu yerda hisoblanmaydi
    is_favorited = serializers.BooleanField(read_only=True, default=False)

    class Meta:
        model = Product
        fields = (
            "id", "slug", "title_uz", "title_ru", "title_en",
            "price", "sale_type", "status", "stock",
            "artisan", "category", "main_image", "gallery", "has_auction",
            "created_at", "rating_avg", "rating_count", "is_favorited",
        )

    def get_main_image(self, obj) -> dict | None:
        image = obj.main_image
        if not image:
            return None
        request = self.context.get("request")
        url = image.image.url
        return {
            "url": request.build_absolute_uri(url) if request else url,
            "alt": image.alt_text,
        }

    def get_gallery(self, obj) -> list:
        """
        Kartadagi almashinadigan rasmlar.

        Asosiy rasm birinchi bo'ladi — sichqoncha hali kartaga tegmaganda
        ko'rinadigan rasm bilan bir xil bo'lishi kerak. To'rttadan ortig'i
        kesiladi: kartaning eni cheklangan, undan ko'p bo'lakka bo'lsak
        har biri sichqoncha uchun juda tor bo'lib qoladi.
        """
        request = self.context.get("request")
        images = sorted(obj.images.all(), key=lambda i: (not i.is_main, i.order, i.id))

        return [
            {
                "url": request.build_absolute_uri(image.image.url)
                if request
                else image.image.url,
                "alt": image.alt_text,
            }
            for image in images[:4]
        ]

    def get_has_auction(self, obj) -> bool:
        return obj.sale_type == Product.SaleType.AUCTION


class ProductDetailSerializer(ProductListSerializer):
    """Mahsulot sahifasi — to'liq tavsif va barcha rasmlar."""

    translated_fields = ("title", "description")
    images = ProductImageSerializer(many=True, read_only=True)
    features = serializers.SerializerMethodField()
    auction_id = serializers.SerializerMethodField()

    class Meta(ProductListSerializer.Meta):
        fields = ProductListSerializer.Meta.fields + (
            # `stock` allaqachon `ProductListSerializer`da bor — takrorlanmaydi
            "description_uz", "description_ru", "description_en",
            "images", "features", "views_count", "auction_id",
        )

    def get_features(self, obj) -> list:
        return [{"name": f.name, "value": f.value} for f in obj.features.all()]

    def get_auction_id(self, obj) -> int | None:
        """Auksion lotimi — frontend "Taklif qilish" tugmasini shu bilan ko'rsatadi."""
        auction = getattr(obj, "auction", None)
        return auction.id if auction else None


class ProductWriteSerializer(serializers.ModelSerializer):
    """
    Hunarmand mahsulot qo'shganda/tahrirlaganda.

    Rasm va xususiyatlar bitta so'rovda keladi — hunarmand formani bir marta
    to'ldirib "Qo'shish" bosadi, ketma-ket bir nechta so'rov yubormaydi.

    `sale_type` ataylab yo'q: auksionni hunarmand emas, admin belgilaydi
    (admin panelda mahsulotni tanlab, narx va sanani qo'yadi — o'shanda
    `sale_type` auksionga o'tadi). Aks holda hunarmand mahsulotni auksion
    deb belgilab qo'yib, lot esa hech qachon ochilmay osilib qolardi.
    """

    images = serializers.ListField(
        child=serializers.ImageField(),
        write_only=True,
        required=False,
        min_length=1,
        max_length=10,
        help_text="1–10 ta rasm",
    )
    # FormData'da murakkab tuzilma yuborish qiyin — JSON matn sifatida qabul qilamiz
    features = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        help_text='JSON: [{"name":"Material","value":"Yong\'och"}]',
    )

    class Meta:
        model = Product
        fields = (
            "id", "slug", "category", "title_uz", "title_ru", "title_en",
            "description_uz", "description_ru", "description_en",
            "price", "stock", "status", "images", "features",
        )
        read_only_fields = ("id", "slug")

    def validate_features(self, value):
        if not value:
            return []

        import json

        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise serializers.ValidationError("Xususiyatlar JSON formatida emas.") from exc

        if not isinstance(parsed, list):
            raise serializers.ValidationError("Xususiyatlar ro'yxat bo'lishi kerak.")

        cleaned = []
        for item in parsed[:20]:
            name = str(item.get("name", "")).strip()[:80]
            val = str(item.get("value", "")).strip()[:160]
            if name and val:
                cleaned.append({"name": name, "value": val})
        return cleaned

    def create(self, validated_data):
        images = validated_data.pop("images", [])
        features = validated_data.pop("features", [])

        # Hunarmandni so'rovdan olamiz — mijoz o'zgartira olmasin
        validated_data["artisan"] = self.context["request"].user.artisan_profile
        product = super().create(validated_data)

        if images:
            ProductImage.objects.bulk_create(
                [
                    ProductImage(product=product, image=image, order=i, is_main=(i == 0))
                    for i, image in enumerate(images)
                ]
            )

        if features:
            ProductFeature.objects.bulk_create(
                [
                    ProductFeature(product=product, order=i, **feature)
                    for i, feature in enumerate(features)
                ]
            )

        return product

    def update(self, instance, validated_data):
        images = validated_data.pop("images", None)
        features = validated_data.pop("features", None)

        # `sold_at` — "bu oy sotilgan" statistikasi shunga tayanadi. Faqat
        # `SOLD`ga birinchi marta o'tganda o'rnatiladi (qayta tahrirlash
        # eskirtirib yubormasin); `SOLD`dan chiqsa tozalanadi, aks holda
        # endi sotilmagan mahsulot hisobda qolib ketadi.
        new_status = validated_data.get("status")
        if new_status == Product.Status.SOLD and instance.status != Product.Status.SOLD:
            validated_data["sold_at"] = timezone.now()
        elif new_status is not None and new_status != Product.Status.SOLD:
            validated_data["sold_at"] = None

        product = super().update(instance, validated_data)

        # Yangi rasm kelsa eskilarini almashtiramiz
        if images:
            product.images.all().delete()
            ProductImage.objects.bulk_create(
                [
                    ProductImage(product=product, image=image, order=i, is_main=(i == 0))
                    for i, image in enumerate(images)
                ]
            )

        if features is not None:
            product.features.all().delete()
            ProductFeature.objects.bulk_create(
                [ProductFeature(product=product, order=i, **f) for i, f in enumerate(features)]
            )

        return product


class ProductFeatureSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductFeature
        fields = ("id", "name", "value")


class CommentSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    user_avatar = serializers.SerializerMethodField()
    is_mine = serializers.SerializerMethodField()
    replies = serializers.SerializerMethodField()
    # "Komentlarim" (o'z mahsulotlariga yozilgan izohlar) ro'yxatida
    # qaysi mahsulotga tegishli ekanini bilish uchun kerak — oddiy
    # per-product izoh ro'yxatida ortiqcha, lekin arzon va zararsiz.
    product_slug = serializers.CharField(source="product.slug", read_only=True)
    product_title = serializers.CharField(source="product.title_uz", read_only=True)
    product_image = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = (
            "id", "text", "rating", "parent", "user_name", "user_avatar",
            "is_mine", "replies", "created_at",
            "product_slug", "product_title", "product_image",
        )
        read_only_fields = ("id", "created_at")

    def get_product_image(self, obj) -> str | None:
        image = obj.product.main_image
        if not image:
            return None
        request = self.context.get("request")
        url = image.image.url
        return request.build_absolute_uri(url) if request else url

    def get_user_name(self, obj) -> str:
        return obj.user.full_name or f"***{obj.user.phone[-4:]}"

    def get_user_avatar(self, obj) -> str | None:
        avatar = obj.user.avatar
        if not avatar:
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(avatar.url) if request else avatar.url

    def get_is_mine(self, obj) -> bool:
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return obj.user_id == request.user.id

    def get_replies(self, obj) -> list:
        # Faqat yuqori darajadagi izohda javoblar chiziladi (bir pog'ona)
        if obj.parent_id is not None:
            return []
        replies = getattr(obj, "prefetched_replies", None)
        if replies is None:
            return []
        return CommentSerializer(replies, many=True, context=self.context).data


class CommentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Comment
        fields = ("id", "text", "rating", "parent")

    def validate_parent(self, value):
        if value and value.parent_id is not None:
            raise serializers.ValidationError("Javobga javob yozib bo'lmaydi.")
        return value

    def validate(self, attrs):
        # Faqat asosiy izohga baho ma'noli — javobga (reply) baho yozib
        # bo'lmaydi, o'rtacha reytingni buzib qo'ymasin
        if attrs.get("parent") is not None:
            attrs["rating"] = None
        return attrs
