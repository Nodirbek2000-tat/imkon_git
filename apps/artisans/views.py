from django.db.models import F
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import CreateAPIView, ListAPIView, RetrieveUpdateAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.common.permissions import IsArtisan

from .models import ArtisanApplication, ArtisanProfile, Craft, Post, PostLike
from .serializers import (
    ApplicationSerializer,
    ArtisanDetailSerializer,
    ArtisanListSerializer,
    ArtisanUpdateSerializer,
    CraftSerializer,
    PostCreateSerializer,
    PostSerializer,
)


class CraftListView(ListAPIView):
    queryset = Craft.objects.all()
    serializer_class = CraftSerializer
    permission_classes = (AllowAny,)
    pagination_class = None


class ArtisanViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/artisans/          — hunarmandlar ro'yxati
    GET /api/artisans/{slug}/   — profil sahifasi
    """

    permission_classes = (AllowAny,)
    lookup_field = "slug"
    search_fields = ("shop_name_uz", "shop_name_ru", "shop_name_en", "region")
    ordering_fields = ("created_at", "products_count", "sold_count")
    ordering = ("-created_at",)

    def get_queryset(self):
        return (
            ArtisanProfile.objects.filter(is_active=True)
            .select_related("user")
            .prefetch_related("crafts")
        )

    def get_serializer_class(self):
        return ArtisanDetailSerializer if self.action == "retrieve" else ArtisanListSerializer


class MyShopView(RetrieveUpdateAPIView):
    """Hunarmand o'z do'konini boshqaradi."""

    serializer_class = ArtisanUpdateSerializer
    permission_classes = (IsArtisan,)

    def get_object(self):
        return self.request.user.artisan_profile


class ApplicationView(CreateAPIView, ListAPIView):
    """
    POST — "Do'kon ochish" arizasini yuborish
    GET  — o'z arizalari tarixi
    """

    serializer_class = ApplicationSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        # Schema generatsiyasida request anonim bo'ladi — bo'sh queryset qaytaramiz
        if getattr(self, "swagger_fake_view", False) or not self.request.user.is_authenticated:
            return ArtisanApplication.objects.none()
        return ArtisanApplication.objects.filter(user=self.request.user).select_related("craft")


class PostViewSet(viewsets.ModelViewSet):
    """
    Instagram uslubidagi postlar.

    GET  /api/posts/?artisan=slug — lenta yoki hunarmand postlari
    POST /api/posts/              — faqat hunarmand
    POST /api/posts/{id}/like/    — like bosish/olib tashlash
    """

    ordering = ("-created_at",)

    def get_queryset(self):
        queryset = (
            Post.objects.filter(is_published=True)
            .select_related("artisan", "artisan__user", "product")
            .prefetch_related("images")
        )
        artisan_slug = self.request.query_params.get("artisan")
        if artisan_slug:
            queryset = queryset.filter(artisan__slug=artisan_slug)
        return queryset

    def get_serializer_class(self):
        return PostCreateSerializer if self.action == "create" else PostSerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [AllowAny()]
        if self.action == "like":
            return [IsAuthenticated()]
        return [IsArtisan()]

    def get_serializer_context(self):
        context = super().get_serializer_context()

        # Sahifadagi postlarning qaysilariga like bosilganini BITTA so'rov
        # bilan olamiz. Har post uchun alohida so'rash N+1 bo'lardi.
        if self.request.user.is_authenticated:
            page_ids = getattr(self, "_page_post_ids", None)
            context["liked_post_ids"] = set(
                PostLike.objects.filter(
                    user=self.request.user,
                    **({"post_id__in": page_ids} if page_ids else {}),
                ).values_list("post_id", flat=True)
            )
        return context

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)

        if page is not None:
            self._page_post_ids = [post.id for post in page]
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def like(self, request, pk=None):
        post = self.get_object()
        like, created = PostLike.objects.get_or_create(post=post, user=request.user)

        if created:
            Post.objects.filter(pk=post.pk).update(likes_count=F("likes_count") + 1)
            return Response({"liked": True}, status=status.HTTP_201_CREATED)

        like.delete()
        Post.objects.filter(pk=post.pk).update(likes_count=F("likes_count") - 1)
        return Response({"liked": False})
