from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import Auction, BidError
from .serializers import (
    AuctionDetailSerializer,
    AuctionListSerializer,
    BidSerializer,
    PlaceBidSerializer,
)


class AuctionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET  /api/auctions/            — lotlar (`?live=1` — faqat jonli)
    GET  /api/auctions/{id}/       — lot sahifasi, taklif tarixi bilan
    POST /api/auctions/{id}/bid/   — narx taklif qilish
    """

    ordering = ("end_at",)

    def get_queryset(self):
        queryset = Auction.objects.with_relations()

        if self.request.query_params.get("live") == "1":
            return queryset.live()

        return queryset.exclude(status=Auction.Status.CANCELLED)

    def get_serializer_class(self):
        return AuctionDetailSerializer if self.action == "retrieve" else AuctionListSerializer

    def get_permissions(self):
        return [IsAuthenticated()] if self.action == "bid" else [AllowAny()]

    def get_throttles(self):
        # ScopedRateThrottle `view.throttle_scope` ni o'qiydi.
        # `@action(throttle_scope=...)` ishlamaydi — as_view() uni rad etadi.
        if self.action == "bid":
            self.throttle_scope = "bid"
        return super().get_throttles()

    def retrieve(self, request, *args, **kwargs):
        auction = self.get_object()

        # Vaqti o'tgan bo'lsa — ko'rish paytida yakunlaymiz.
        # Shu bilan doimiy ishlaydigan fon-vazifasiz ham holat to'g'ri qoladi.
        if auction.status == Auction.Status.LIVE and timezone.now() >= auction.end_at:
            auction.finalize()
            auction.refresh_from_db()

        serializer = self.get_serializer(auction)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def bid(self, request, pk=None):
        auction = self.get_object()

        serializer = PlaceBidSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        amount = (
            auction.next_min_bid
            if serializer.validated_data["increment"]
            else serializer.validated_data["amount"]
        )

        try:
            bid = Auction.place_bid(auction.pk, request.user, amount)
        except BidError as exc:
            return Response(
                {"detail": exc.messages[0] if exc.messages else str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        auction.refresh_from_db()

        # Narxlar satr sifatida — Decimal'ni to'g'ridan-to'g'ri qaytarsak
        # JSON'ga float bo'lib tushadi va qolgan endpoint'lardan farq qiladi
        # (ular `DecimalField` orqali "60000.00" beradi).
        return Response(
            {
                "bid": BidSerializer(bid, context={"request": request}).data,
                "current_price": f"{auction.current_price:.2f}",
                "next_min_bid": f"{auction.next_min_bid:.2f}",
                "end_at": auction.end_at,
                "bids_count": auction.bids_count,
            },
            status=status.HTTP_201_CREATED,
        )
