from django.db.models import Count, F, Prefetch, Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import (
    CreateAPIView,
    ListAPIView,
    ListCreateAPIView,
    RetrieveUpdateAPIView,
)
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.common.permissions import IsArtisan, IsSchool

from .models import ArtisanApplication, ArtisanProfile, Craft, Post, PostLike, SchoolProfile
from .serializers import (
    ApplicationSerializer,
    ArtisanDetailSerializer,
    ArtisanListSerializer,
    ArtisanUpdateSerializer,
    CraftSerializer,
    PostCreateSerializer,
    PostSerializer,
    SchoolDetailSerializer,
    SchoolListSerializer,
    SchoolUpdateSerializer,
    StudentSerializer,
    StudentWriteSerializer,
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
        queryset = (
            ArtisanProfile.objects.filter(is_active=True)
            # Maktab o'chirilsa uning o'quvchilari sahifasi ham yopiladi.
            # `exclude` — oddiy hunarmandda `school` NULL va u shartga
            # tushmaydi, ya'ni hunarmandlar bunga sezgir emas.
            .exclude(school__is_active=False)
            .select_related("user", "school")
            .prefetch_related("crafts")
        )

        # RO'YXATDA faqat hunarmandlar. O'quvchilar "Hunarmandlar"
        # bo'limida chiqmaydi — ular maktab sahifasida ko'rinadi.
        #
        # `retrieve` da esa filtr QO'YILMAYDI: o'quvchining o'z sahifasi
        # (`/hunarmand/<slug>`) ochilishi kerak, aks holda mahsulot
        # kartasidagi havola 404 berardi.
        if self.action == "list":
            queryset = queryset.filter(kind=ArtisanProfile.Kind.ARTISAN)

        return queryset

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


# ====================================================================
#                             MAKTABLAR
# ====================================================================


class SchoolViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/schools/          — maktablar ro'yxati
    GET /api/schools/{slug}/   — maktab sahifasi, o'quvchilari bilan
    """

    permission_classes = (AllowAny,)
    lookup_field = "slug"
    search_fields = ("name_uz", "name_ru", "name_en", "region", "district")
    ordering_fields = ("name_uz", "students_count", "created_at")
    ordering = ("name_uz",)

    def get_queryset(self):
        queryset = SchoolProfile.objects.filter(is_active=True).annotate(
            # Ommaviy sahifada yashirilgan o'quvchi sanalmaydi — serializer
            # shu annotatsiyani o'qiydi (izohi `SchoolListSerializer` da)
            visible_students=Count("students", filter=Q(students__is_active=True))
        )

        if self.action == "retrieve":
            # O'quvchilarni bitta so'rov bilan olamiz — har biri uchun
            # alohida so'rov ketsa sahifa N+1 bo'lib sekinlashardi
            students = ArtisanProfile.objects.select_related("user").order_by(
                "user__full_name"
            )
            queryset = queryset.prefetch_related(
                Prefetch("students", queryset=students)
            )

        return queryset

    def get_serializer_class(self):
        return SchoolDetailSerializer if self.action == "retrieve" else SchoolListSerializer


class MySchoolView(RetrieveUpdateAPIView):
    """Maktab o'z sahifasini ko'radi va tahrirlaydi."""

    serializer_class = SchoolUpdateSerializer
    permission_classes = (IsSchool,)

    def get_object(self):
        return self.request.user.school_profile


class SchoolStudentListView(ListCreateAPIView):
    """
    GET  /api/school/students/ — maktabning o'z o'quvchilari
    POST /api/school/students/ — yangi o'quvchi (tasdiqlashsiz, darhol)
    """

    permission_classes = (IsSchool,)
    pagination_class = None  # maktabda o'quvchi ko'p bo'lmaydi

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ArtisanProfile.objects.none()
        # `school__user` orqali — maktab FAQAT o'z o'quvchilarini ko'radi
        return (
            ArtisanProfile.objects.filter(school__user=self.request.user)
            .select_related("user")
            .order_by("user__full_name")
        )

    def get_serializer_class(self):
        return StudentWriteSerializer if self.request.method == "POST" else StudentSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        user = self.request.user
        if user.is_authenticated and getattr(user, "is_school", False):
            context["school"] = user.school_profile
        return context

    def create(self, request, *args, **kwargs):
        serializer = StudentWriteSerializer(
            data=request.data, context=self.get_serializer_context()
        )
        serializer.is_valid(raise_exception=True)
        profile = serializer.save()

        # Javobda O'QISH serializeri — frontend ro'yxatga shu zahoti
        # qo'sha oladi, qayta so'rov yubormasdan
        return Response(
            StudentSerializer(profile, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )


class SchoolStudentDetailView(RetrieveUpdateAPIView):
    """
    Bitta o'quvchini ko'rish/tahrirlash.

    O'chirish YO'Q: o'chirish bolaning mahsulotlarini, ular orqali
    buyurtma tarixini ham olib ketardi. O'rniga `is_active=false` —
    o'quvchi sahifalardan yo'qoladi, ma'lumot esa joyida qoladi.
    """

    permission_classes = (IsSchool,)
    lookup_field = "slug"

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ArtisanProfile.objects.none()
        return ArtisanProfile.objects.filter(
            school__user=self.request.user
        ).select_related("user")

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return StudentWriteSerializer
        return StudentSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        user = self.request.user
        if user.is_authenticated and getattr(user, "is_school", False):
            context["school"] = user.school_profile
        return context

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = StudentWriteSerializer(
            instance,
            data=request.data,
            partial=request.method == "PATCH",
            context=self.get_serializer_context(),
        )
        serializer.is_valid(raise_exception=True)
        profile = serializer.save()
        return Response(
            StudentSerializer(profile, context=self.get_serializer_context()).data
        )


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
