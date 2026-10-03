from django.db import transaction
from django.db.models import F
from rest_framework import serializers

from apps.accounts.models import User
from apps.accounts.serializers import PublicUserSerializer
from apps.common.translation import TranslatedSerializerMixin, resolve_language

from .models import (
    ArtisanApplication,
    ArtisanProfile,
    Craft,
    Post,
    PostImage,
    SchoolProfile,
)


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
            "user", "crafts", "region", "banner", "kind",
            "products_count", "posts_count", "sold_count", "created_at",
        )


class ArtisanDetailSerializer(ArtisanListSerializer):
    """Hunarmand profili — Instagram sahifasiga o'xshash."""

    translated_fields = ("shop_name", "about")

    # O'quvchining sahifasida uning maktabi ko'rinadi va bosilsa maktab
    # sahifasiga olib boradi. Oddiy hunarmandda `null`.
    school = serializers.SerializerMethodField()

    class Meta(ArtisanListSerializer.Meta):
        fields = ArtisanListSerializer.Meta.fields + (
            "about_uz", "about_ru", "about_en", "school", "student_grade",
        )

    def get_school(self, obj) -> dict | None:
        if not obj.school_id:
            return None
        lang = resolve_language(self.context.get("request"))
        return {
            "slug": obj.school.slug,
            "name": obj.school.tr("name", lang),
            "logo": self._absolute(obj.school.logo),
            "region": obj.school.region,
            "district": obj.school.district,
        }

    def _absolute(self, image) -> str | None:
        if not image:
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(image.url) if request else image.url


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

        # Maktab va o'quvchi ariza yubormaydi: maktabni admin ochadi,
        # o'quvchini maktab kiritadi. Ariza tasdiqlansa `role` `artisan`ga
        # o'tib ketardi — maktab o'z loginini va o'quvchilarini,
        # o'quvchi esa maktab bilan aloqasini yo'qotardi.
        if user.is_school or user.is_student:
            raise serializers.ValidationError(
                "Maktab va o'quvchi akkaunti bu arizani yubormaydi."
            )

        if ArtisanApplication.objects.filter(
            user=user, status=ArtisanApplication.Status.PENDING
        ).exists():
            raise serializers.ValidationError("Sizda ko'rib chiqilayotgan ariza bor.")

        return attrs

    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)


# ====================================================================
#                             MAKTABLAR
# ====================================================================


class StudentSerializer(serializers.ModelSerializer):
    """
    Maktab o'quvchisi — o'qish uchun.

    O'quvchi `ArtisanProfile` da saqlanadi (`kind="student"`), shuning
    uchun uning ishlari katalogga, auksionga va buyurtmaga hech qanday
    qo'shimcha kodsiz tushadi.
    """

    full_name = serializers.CharField(source="user.full_name", read_only=True)
    avatar = serializers.ImageField(source="user.avatar", read_only=True)

    class Meta:
        model = ArtisanProfile
        fields = (
            "id", "slug", "full_name", "avatar", "student_grade",
            "products_count", "sold_count", "is_active", "created_at",
        )


class StudentWriteSerializer(serializers.Serializer):
    """
    Maktab o'quvchi kiritadi/tahrirlaydi.

    Hech qanday tasdiqlash yo'q: maktab ismni yozib "Saqlash" bosadi va
    o'quvchi shu zahoti paydo bo'ladi. Admin aralashmaydi.

    `Serializer` (ModelSerializer emas) — chunki bitta forma IKKITA
    qatorni yaratadi: `User` (o'quvchi akkaunti) va `ArtisanProfile`
    (uning ommaviy sahifasi).
    """

    full_name = serializers.CharField(max_length=120)
    student_grade = serializers.CharField(
        max_length=20, required=False, allow_blank=True, default=""
    )
    avatar = serializers.ImageField(required=False, allow_null=True)
    about = serializers.CharField(
        max_length=1500, required=False, allow_blank=True, default=""
    )
    is_active = serializers.BooleanField(required=False)

    def validate_full_name(self, value: str) -> str:
        name = " ".join(value.split())
        if len(name) < 3:
            raise serializers.ValidationError("Ism-familiyani to'liq yozing.")
        return name

    @transaction.atomic
    def create(self, validated_data):
        school = self.context["school"]
        full_name = validated_data["full_name"]

        # `create_student` — telefon va parol talab qilmaydigan yagona yo'l.
        # O'quvchi tizimga kirmaydi, akkaunt faqat ishlarini unga bog'lash
        # uchun kerak (buyurtma, auksion, statistika hammasi `user` ga
        # tayanadi).
        user = User.objects.create_student(full_name=full_name)
        if validated_data.get("avatar"):
            user.avatar = validated_data["avatar"]
            user.save(update_fields=["avatar", "updated_at"])

        profile = ArtisanProfile.objects.create(
            user=user,
            kind=ArtisanProfile.Kind.STUDENT,
            school=school,
            student_grade=validated_data.get("student_grade", ""),
            # Do'kon nomi — bolaning o'z ismi. Mahsulot kartasida ham,
            # auksion lotida ham kimning ishi ekani shundan ko'rinadi.
            shop_name_uz=full_name,
            about_uz=validated_data.get("about", ""),
            region=school.region,
        )

        # COUNT(*) o'rniga saqlangan sanoq — F() bilan, poyga holatisiz
        SchoolProfile.objects.filter(pk=school.pk).update(
            students_count=F("students_count") + 1
        )
        return profile

    @transaction.atomic
    def update(self, instance, validated_data):
        user = instance.user

        user_fields = []
        if "full_name" in validated_data:
            user.full_name = validated_data["full_name"]
            instance.shop_name_uz = validated_data["full_name"]
            user_fields.append("full_name")
        if validated_data.get("avatar"):
            user.avatar = validated_data["avatar"]
            user_fields.append("avatar")
        if user_fields:
            user.save(update_fields=user_fields + ["updated_at"])

        if "student_grade" in validated_data:
            instance.student_grade = validated_data["student_grade"]
        if "about" in validated_data:
            instance.about_uz = validated_data["about"]
        if "is_active" in validated_data:
            # O'quvchi o'chirilmaydi, FAQAT yashiriladi: o'chirish uning
            # mahsulotlarini, ular orqali buyurtma tarixini ham yetaklab
            # ketardi (`Product.artisan` CASCADE).
            instance.is_active = validated_data["is_active"]

        instance.save()
        return instance


class SchoolListSerializer(TranslatedSerializerMixin, serializers.ModelSerializer):
    """Maktablar ro'yxati."""

    translated_fields = ("name",)

    # Ommaviy sahifada FAQAT ko'rinadigan o'quvchilar sanaladi.
    # Modeldagi `students_count` — jami son, yashirilganlari bilan birga
    # (admin shuni ko'rishi kerak). Ikkisini aralashtirsak xaridor
    # ro'yxatda "5 o'quvchi" deb o'qib, maktab sahifasida 3 tasini
    # ko'rardi — bu saytga ishonchni yo'qotadi.
    students_count = serializers.SerializerMethodField()

    class Meta:
        model = SchoolProfile
        fields = (
            "id", "slug", "name_uz", "name_ru", "name_en",
            "region", "district", "logo", "banner",
            "students_count", "created_at",
        )

    def get_students_count(self, obj) -> int:
        # `visible_students` — `SchoolViewSet` annotatsiyasi. Bo'lmasa
        # (boshqa joydan chaqirilsa) ko'rinadigan o'quvchilarni sanaymiz.
        annotated = getattr(obj, "visible_students", None)
        if annotated is not None:
            return annotated
        return sum(1 for s in obj.students.all() if s.is_active)


class SchoolDetailSerializer(SchoolListSerializer):
    """Maktab sahifasi — o'quvchilari bilan birga."""

    translated_fields = ("name", "about")

    students = serializers.SerializerMethodField()

    class Meta(SchoolListSerializer.Meta):
        fields = SchoolListSerializer.Meta.fields + (
            "about_uz", "about_ru", "about_en", "contact_phone", "students",
        )

    def get_students(self, obj) -> list:
        # Yashirilgan o'quvchi ommaviy sahifada ko'rinmaydi
        students = [s for s in obj.students.all() if s.is_active]
        return StudentSerializer(students, many=True, context=self.context).data


class SchoolUpdateSerializer(serializers.ModelSerializer):
    """
    Maktab o'z sahifasini tahrirlaydi.

    `login` bu yerda YO'Q — uni faqat platforma admini o'zgartiradi,
    aks holda maktab o'z kirish yo'lini o'zi buzib qo'yishi mumkin edi.
    """

    login = serializers.CharField(read_only=True)
    students_count = serializers.IntegerField(read_only=True)
    slug = serializers.CharField(read_only=True)

    class Meta:
        model = SchoolProfile
        fields = (
            "id", "slug", "login",
            "name_uz", "name_ru", "name_en",
            "about_uz", "about_ru", "about_en",
            "region", "district", "contact_phone",
            "logo", "banner", "students_count",
        )
