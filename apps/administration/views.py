from datetime import timedelta

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.generics import ListAPIView, ListCreateAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.sms import SMSError, send_sms
from apps.artisans.models import ArtisanApplication, ArtisanProfile
from apps.auctions.models import Auction, Bid
from apps.catalog.models import Product
from apps.notifications.models import Notification
from apps.payments.models import PaymentCard

from .permissions import IsPlatformAdmin
from .serializers import (
    AdminApplicationSerializer,
    AdminAuctionSerializer,
    AdminPaymentCardSerializer,
    AdminUserSerializer,
    AuctionCandidateSerializer,
    AuctionCreateSerializer,
    ReviewApplicationSerializer,
    StatsSerializer,
)


class StatsView(APIView):
    """Admin panel bosh sahifasi — bitta so'rovda barcha raqamlar."""

    permission_classes = (IsPlatformAdmin,)

    def get(self, request):
        week_ago = timezone.now() - timedelta(days=7)

        # Har bir raqam uchun alohida COUNT o'rniga agregatlarni birlashtiramiz
        user_stats = User.objects.aggregate(
            users_total=Count("id"),
            users_new_week=Count("id", filter=Q(created_at__gte=week_ago)),
            artisans_total=Count("id", filter=Q(role=User.Role.ARTISAN)),
            admins_total=Count("id", filter=Q(is_staff=True)),
        )
        application_stats = ArtisanApplication.objects.aggregate(
            applications_total=Count("id"),
            applications_pending=Count(
                "id", filter=Q(status=ArtisanApplication.Status.PENDING)
            ),
        )
        product_stats = Product.objects.aggregate(
            products_total=Count("id"),
            products_active=Count("id", filter=Q(status=Product.Status.ACTIVE)),
        )

        now = timezone.now()
        auction_stats = Auction.objects.aggregate(
            auctions_total=Count("id"),
            auctions_live=Count(
                "id",
                filter=Q(status=Auction.Status.LIVE, start_at__lte=now, end_at__gt=now),
            ),
        )

        data = {
            **user_stats,
            **application_stats,
            **product_stats,
            **auction_stats,
            "bids_total": Bid.objects.count(),
        }
        return Response(StatsSerializer(data).data)


class AdminUserListView(ListAPIView):
    """Foydalanuvchilar ro'yxati. `?role=artisan`, `?admins=1`, `?search=`"""

    serializer_class = AdminUserSerializer
    permission_classes = (IsPlatformAdmin,)
    search_fields = ("phone", "full_name")
    ordering_fields = ("created_at", "full_name")
    ordering = ("-created_at",)

    def get_queryset(self):
        queryset = User.objects.select_related("artisan_profile")

        role = self.request.query_params.get("role")
        if role in (User.Role.USER, User.Role.ARTISAN):
            queryset = queryset.filter(role=role)

        if self.request.query_params.get("admins") == "1":
            queryset = queryset.filter(is_staff=True)

        return queryset


class ApplicationListView(ListAPIView):
    """Kelib tushgan arizalar. `?status=pending` (default — barchasi)"""

    serializer_class = AdminApplicationSerializer
    permission_classes = (IsPlatformAdmin,)
    ordering = ("-created_at",)

    def get_queryset(self):
        queryset = ArtisanApplication.objects.select_related(
            "user", "user__artisan_profile", "craft"
        )
        status_filter = self.request.query_params.get("status")
        if status_filter in ArtisanApplication.Status.values:
            queryset = queryset.filter(status=status_filter)
        return queryset.order_by("-created_at")


@api_view(["POST"])
@permission_classes([IsPlatformAdmin])
def approve_application(request, pk):
    """
    Arizani tasdiqlash → hunarmand profili ochiladi, rol o'zgaradi.

    Bitta tranzaksiyada: profil yaratish, rolni ko'tarish, arizani belgilash.
    Oraliqda xato bo'lsa hech narsa qolmaydi — yarim ochilgan do'kon bo'lmasin.
    """
    try:
        application = ArtisanApplication.objects.select_related("user", "craft").get(pk=pk)
    except ArtisanApplication.DoesNotExist:
        return Response({"detail": "Ariza topilmadi."}, status=status.HTTP_404_NOT_FOUND)

    if application.status != ArtisanApplication.Status.PENDING:
        return Response(
            {"detail": "Bu ariza allaqachon ko'rib chiqilgan."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    serializer = ReviewApplicationSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    with transaction.atomic():
        profile, _ = ArtisanProfile.objects.get_or_create(
            user=application.user,
            defaults={
                "shop_name_uz": application.shop_name,
                "about_uz": application.description,
                "region": application.region,
            },
        )
        profile.crafts.add(application.craft)

        application.user.promote_to_artisan()

        application.status = ArtisanApplication.Status.APPROVED
        application.admin_note = serializer.validated_data.get("note", "")
        application.reviewed_at = timezone.now()
        application.save(update_fields=["status", "admin_note", "reviewed_at", "updated_at"])

    Notification.notify(
        application.user,
        type=Notification.Type.APPLICATION_APPROVED,
        title="Arizangiz tasdiqlandi!",
        body="Tabriklaymiz — endi do'koningiz ochiq, mahsulot qo'sha olasiz.",
        link_url="/profil",
    )

    # SMS tranzaksiyadan TASHQARIDA — provayder ishlamasa ham tasdiq qolsin
    try:
        send_sms(
            application.user.phone,
            "Imkon: arizangiz tasdiqlandi! Endi mahsulot qo'sha olasiz.",
        )
    except SMSError:
        pass

    return Response(
        {
            "detail": "Ariza tasdiqlandi.",
            "artisan_slug": profile.slug,
            "application": AdminApplicationSerializer(application).data,
        }
    )


@api_view(["POST"])
@permission_classes([IsPlatformAdmin])
def reject_application(request, pk):
    try:
        application = ArtisanApplication.objects.select_related("user").get(pk=pk)
    except ArtisanApplication.DoesNotExist:
        return Response({"detail": "Ariza topilmadi."}, status=status.HTTP_404_NOT_FOUND)

    if application.status != ArtisanApplication.Status.PENDING:
        return Response(
            {"detail": "Bu ariza allaqachon ko'rib chiqilgan."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    serializer = ReviewApplicationSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    application.status = ArtisanApplication.Status.REJECTED
    application.admin_note = serializer.validated_data.get("note", "")
    application.reviewed_at = timezone.now()
    application.save(update_fields=["status", "admin_note", "reviewed_at", "updated_at"])

    note = application.admin_note
    Notification.notify(
        application.user,
        type=Notification.Type.APPLICATION_REJECTED,
        title="Arizangiz rad etildi",
        body=(f"Sabab: {note}" if note else "Batafsil ma'lumot uchun biz bilan bog'laning.")
        + " Xohlasangiz qaytadan ariza topshirishingiz mumkin.",
        link_url="/profil",
    )

    return Response({"detail": "Ariza rad etildi."})


@api_view(["POST"])
@permission_classes([IsPlatformAdmin])
def toggle_admin(request, pk):
    """Foydalanuvchini admin qilish yoki huquqini olib tashlash."""
    try:
        target = User.objects.get(pk=pk)
    except User.DoesNotExist:
        return Response({"detail": "Foydalanuvchi topilmadi."}, status=status.HTTP_404_NOT_FOUND)

    if target.pk == request.user.pk:
        return Response(
            {"detail": "O'zingizdan admin huquqini olib tashlay olmaysiz."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if target.is_superuser and not request.user.is_superuser:
        return Response(
            {"detail": "Superuser huquqini faqat superuser o'zgartira oladi."},
            status=status.HTTP_403_FORBIDDEN,
        )

    target.is_staff = not target.is_staff
    target.save(update_fields=["is_staff", "updated_at"])

    if target.is_staff:
        try:
            send_sms(target.phone, "Imkon: sizga admin huquqi berildi.")
        except SMSError:
            pass

    return Response(
        {
            "detail": "Admin qilindi." if target.is_staff else "Admin huquqi olib tashlandi.",
            "user": AdminUserSerializer(target).data,
        }
    )


@api_view(["POST"])
@permission_classes([IsPlatformAdmin])
def toggle_user_active(request, pk):
    """Akkauntni bloklash / blokdan chiqarish."""
    try:
        target = User.objects.get(pk=pk)
    except User.DoesNotExist:
        return Response({"detail": "Foydalanuvchi topilmadi."}, status=status.HTTP_404_NOT_FOUND)

    if target.pk == request.user.pk:
        return Response(
            {"detail": "O'zingizni bloklay olmaysiz."}, status=status.HTTP_400_BAD_REQUEST
        )

    target.is_active = not target.is_active
    target.save(update_fields=["is_active", "updated_at"])

    return Response(
        {
            "detail": "Blokdan chiqarildi." if target.is_active else "Bloklandi.",
            "user": AdminUserSerializer(target).data,
        }
    )


class AdminAuctionListView(ListAPIView):
    serializer_class = AdminAuctionSerializer
    permission_classes = (IsPlatformAdmin,)

    def get_queryset(self):
        return Auction.objects.select_related(
            "product", "product__artisan", "winner"
        ).order_by("-created_at")


class PaymentCardListView(ListCreateAPIView):
    """
    To'lov kartalari — ro'yxat va yangisini qo'shish.

    Yangi qo'shilgan karta darrov faol bo'ladi: admin karta qo'shayotgan
    bo'lsa, demak pul aynan o'shanga tushishi kerak. Qo'shib, keyin alohida
    "faollashtirish" tugmasini qidirib yurish ortiqcha qadam bo'lardi.
    """

    serializer_class = AdminPaymentCardSerializer
    permission_classes = (IsPlatformAdmin,)
    pagination_class = None

    def get_queryset(self):
        return PaymentCard.objects.all()

    def perform_create(self, serializer):
        card = serializer.save()
        PaymentCard.make_active(card.pk)
        card.refresh_from_db()


@api_view(["POST"])
@permission_classes([IsPlatformAdmin])
def activate_card(request, pk):
    """Kartani faollashtirish — qolganlari avtomatik o'chadi."""
    if not PaymentCard.objects.filter(pk=pk).exists():
        return Response({"detail": "Karta topilmadi."}, status=status.HTTP_404_NOT_FOUND)

    card = PaymentCard.make_active(pk)
    return Response(
        {
            "detail": "Karta faollashtirildi. To'lovlar shu kartaga yo'naltiriladi.",
            "card": AdminPaymentCardSerializer(card).data,
        }
    )


@api_view(["POST"])
@permission_classes([IsPlatformAdmin])
def deactivate_card(request, pk):
    """
    Kartani o'chirish.

    Boshqa faol karta qolmasa ogohlantiramiz — faol kartasiz bot to'lovni
    umuman boshlay olmaydi va xaridor "karta sozlanmagan" degan xabarni
    ko'radi.
    """
    card = PaymentCard.objects.filter(pk=pk).first()
    if card is None:
        return Response({"detail": "Karta topilmadi."}, status=status.HTTP_404_NOT_FOUND)

    card.is_active = False
    card.save(update_fields=["is_active", "updated_at"])

    others = PaymentCard.objects.filter(is_active=True).exists()
    return Response(
        {
            "detail": (
                "Karta o'chirildi."
                if others
                else "Karta o'chirildi. Endi faol karta yo'q — to'lovlar to'xtaydi!"
            ),
            "has_active": others,
            "card": AdminPaymentCardSerializer(card).data,
        }
    )


class AuctionCandidateListView(ListAPIView):
    """
    Auksionga qo'yish mumkin bo'lgan mahsulotlar.

    Admin panelda ro'yxatdan tanlanadi — slug'ni qo'lda yozdirmaymiz.
    """

    serializer_class = AuctionCandidateSerializer
    permission_classes = (IsPlatformAdmin,)
    search_fields = ("title_uz", "artisan__shop_name_uz")

    def get_queryset(self):
        return (
            Product.objects.filter(auction__isnull=True)
            .exclude(status=Product.Status.SOLD)
            .select_related("artisan")
            .prefetch_related("images")
            .order_by("-created_at")
        )


class AuctionCreateView(APIView):
    """Admin yangi auksion ochadi."""

    permission_classes = (IsPlatformAdmin,)

    def post(self, request):
        serializer = AuctionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        auction = serializer.save()

        return Response(
            AdminAuctionSerializer(auction).data, status=status.HTTP_201_CREATED
        )


@api_view(["POST"])
@permission_classes([IsPlatformAdmin])
def finalize_auction(request, pk):
    """Auksionni yakunlash — g'olib aniqlanadi."""
    try:
        auction = Auction.objects.get(pk=pk)
    except Auction.DoesNotExist:
        return Response({"detail": "Auksion topilmadi."}, status=status.HTTP_404_NOT_FOUND)

    if auction.status != Auction.Status.LIVE:
        return Response(
            {"detail": "Faqat jonli auksionni yakunlash mumkin."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # `finalize()` vaqt tugamagan bo'lsa hech narsa qilmaydi —
    # admin majburan yakunlaganda vaqtni hozirgi paytga tushiramiz
    if timezone.now() < auction.end_at:
        auction.end_at = timezone.now()
        auction.save(update_fields=["end_at", "updated_at"])

    auction.finalize()
    auction.refresh_from_db()

    return Response(
        {
            "detail": "Auksion yakunlandi.",
            "auction": AdminAuctionSerializer(auction).data,
        }
    )


@api_view(["POST"])
@permission_classes([IsPlatformAdmin])
def cancel_auction(request, pk):
    try:
        auction = Auction.objects.get(pk=pk)
    except Auction.DoesNotExist:
        return Response({"detail": "Auksion topilmadi."}, status=status.HTTP_404_NOT_FOUND)

    if auction.status in (Auction.Status.ENDED, Auction.Status.CANCELLED):
        return Response(
            {"detail": "Bu auksion allaqachon yopilgan."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    auction.status = Auction.Status.CANCELLED
    auction.save(update_fields=["status", "updated_at"])

    return Response({"detail": "Auksion bekor qilindi."})
