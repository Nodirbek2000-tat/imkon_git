from django.db.models import F
from rest_framework import serializers

from apps.accounts.serializers import PublicUserSerializer
from apps.common.translation import TranslatedSerializerMixin

from .models import ArtisanApplication, ArtisanProfile, Craft, Post, PostImage


class CraftSerializer(TranslatedSerializerMixin, serializers.ModelSerializer):
    translated_fields = ("name",)

    class Meta:
        model = Craft
        fields = ("id", "slug", "name_uz", "name_ru", "name_en", "icon")


class ArtisanListSerializer(TranslatedSerializerMixin, serializers.ModelSerializer):
    """Hunarmandlar ro'yxati."""

    translated_fields = ("shop_name",)

    user = PublicUserSerializer(read_only=True)
    crafts = CraftSerializer(many=True, read_only=True)

    class Meta:
        model = ArtisanProfile
        fields = (
            "id", "slug", "shop_name_uz", "shop_name_ru", "shop_name_en",
            "user", "crafts", "region", "banner",
            "products_count", "posts_count", "sold_count", "created_at",
        )


class ArtisanDetailSerializer(ArtisanListSerializer):
    """Hunarmand profili — Instagram sahifasiga o'xshash."""

    translated_fields = ("shop_name", "about")

    class Meta(ArtisanListSerializer.Meta):
        fields = ArtisanListSerializer.Meta.fields + (
            "about_uz", "about_ru", "about_en",
        )


class ArtisanUpdateSerializer(serializers.ModelSerializer):
    """Hunarmand o'z do'konini tahrirlaydi."""

    class Meta:
        model = ArtisanProfile
        fields = (
            "shop_name_uz", "shop_name_ru", "shop_name_en",
            "about_uz", "about_ru", "about_en",
            "crafts", "region", "banner",
        )


class PostImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = PostImage
        fields = ("id", "image", "order")


class PostSerializer(serializers.ModelSerializer):
    images = PostImageSerializer(many=True, read_only=True)
    artisan_slug = serializers.CharField(source="artisan.slug", read_only=True)
    artisan_name = serializers.SerializerMethodField()
    artisan_avatar = serializers.SerializerMethodField()
    is_liked = serializers.SerializerMethodField()

    class Meta:
        model = Post
        fields = (
            "id", "caption", "images", "product",
            "artisan_slug", "artisan_name", "artisan_avatar",
            "likes_count", "is_liked", "created_at",
        )
        read_only_fields = ("likes_count",)

    def get_artisan_name(self, obj) -> str:
        from apps.common.translation import resolve_language

        return obj.artisan.tr("shop_name", resolve_language(self.context.get("request")))

    def get_artisan_avatar(self, obj) -> str | None:
        avatar = obj.artisan.user.avatar
        if not avatar:
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(avatar.url) if request else avatar.url

    def get_is_liked(self, obj) -> bool:
        # `liked_post_ids` view'da bitta so'rov bilan yig'iladi (N+1 yo'q)
        liked = self.context.get("liked_post_ids")
        return obj.id in liked if liked is not None else False


class PostCreateSerializer(serializers.ModelSerializer):
    images = serializers.ListField(
        child=serializers.ImageField(), write_only=True, min_length=1, max_length=10
    )

    class Meta:
        model = Post
        fields = ("id", "caption", "product", "images")

    def create(self, validated_data):
        images = validated_data.pop("images")
        artisan = self.context["request"].user.artisan_profile

        post = Post.objects.create(artisan=artisan, **validated_data)
        PostImage.objects.bulk_create(
            [PostImage(post=post, image=image, order=i) for i, image in enumerate(images)]
        )

        ArtisanProfile.objects.filter(pk=artisan.pk).update(posts_count=F("posts_count") + 1)
        return post


class ApplicationSerializer(serializers.ModelSerializer):
    """"Do'kon ochish" arizasi."""

    class Meta:
        model = ArtisanApplication
        fields = (
            "id", "shop_name", "craft", "description", "region", "document",
            "status", "admin_note", "created_at", "reviewed_at",
        )
        read_only_fields = ("status", "admin_note", "reviewed_at")

    def validate(self, attrs):
        user = self.context["request"].user

        if user.is_artisan:
            raise serializers.ValidationError("Siz allaqachon hunarmandsiz.")

        if ArtisanApplication.objects.filter(
            user=user, status=ArtisanApplication.Status.PENDING
        ).exists():
            raise serializers.ValidationError("Sizda ko'rib chiqilayotgan ariza bor.")

        return attrs

    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)
