"""
Auksion — eng nozik joy. Narx bilan bog'liq mantiq buzilsa pul yo'qoladi,
shuning uchun har bir qoida alohida tekshiriladi.
"""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.artisans.models import ArtisanProfile, Craft
from apps.auctions.models import Auction, BidError
from apps.catalog.models import Category, Product


class AuctionBidTests(TestCase):
    def setUp(self):
        self.craft = Craft.objects.create(slug="kulol", name_uz="Kulolchilik")
        self.category = Category.objects.create(slug="idish", name_uz="Idishlar")

        self.artisan_user = User.objects.create_user(
            phone="+998901112233", full_name="Malika Yusupova", role=User.Role.ARTISAN
        )
        self.artisan = ArtisanProfile.objects.create(
            user=self.artisan_user, shop_name_uz="Rishton kulollari"
        )

        self.buyer = User.objects.create_user(phone="+998901112234", full_name="Aziz Rahimov")
        self.other = User.objects.create_user(phone="+998901112235", full_name="Nodir Karimov")

        self.product = Product.objects.create(
            artisan=self.artisan,
            category=self.category,
            title_uz="Sopol choynak",
            price=Decimal("200000"),
            sale_type=Product.SaleType.AUCTION,
            status=Product.Status.ACTIVE,
        )
        self.auction = Auction.objects.create(
            product=self.product,
            start_price=Decimal("200000"),
            min_increment=Decimal("10000"),
            start_at=timezone.now() - timedelta(hours=1),
            end_at=timezone.now() + timedelta(hours=5),
            status=Auction.Status.LIVE,
        )

    # ------------------------------------------------------------ asosiy

    def test_first_bid_must_meet_start_price(self):
        self.assertEqual(self.auction.next_min_bid, Decimal("200000"))

        with self.assertRaises(BidError):
            Auction.place_bid(self.auction.pk, self.buyer, Decimal("199999"))

    def test_successful_bid_updates_price_and_count(self):
        Auction.place_bid(self.auction.pk, self.buyer, Decimal("200000"))
        self.auction.refresh_from_db()

        self.assertEqual(self.auction.current_price, Decimal("200000"))
        self.assertEqual(self.auction.bids_count, 1)
        # Keyingi taklif kamida joriy narx + qadam
        self.assertEqual(self.auction.next_min_bid, Decimal("210000"))

    def test_bid_below_increment_is_rejected(self):
        Auction.place_bid(self.auction.pk, self.buyer, Decimal("200000"))

        with self.assertRaises(BidError) as ctx:
            Auction.place_bid(self.auction.pk, self.other, Decimal("205000"))

        self.assertIn("210000", str(ctx.exception))

    # ------------------------------------------------------------ qoidalar

    def test_artisan_cannot_bid_on_own_lot(self):
        with self.assertRaises(BidError) as ctx:
            Auction.place_bid(self.auction.pk, self.artisan_user, Decimal("300000"))

        self.assertIn("O'z lotingizga", str(ctx.exception))

    def test_cannot_outbid_yourself(self):
        Auction.place_bid(self.auction.pk, self.buyer, Decimal("200000"))

        with self.assertRaises(BidError) as ctx:
            Auction.place_bid(self.auction.pk, self.buyer, Decimal("250000"))

        self.assertIn("eng yuqori taklifni", str(ctx.exception))

    def test_cannot_bid_after_end(self):
        self.auction.end_at = timezone.now() - timedelta(seconds=1)
        self.auction.save(update_fields=["end_at"])

        with self.assertRaises(BidError):
            Auction.place_bid(self.auction.pk, self.buyer, Decimal("500000"))

    # ------------------------------------------------------------ anti-sniping

    def test_late_bid_extends_deadline(self):
        self.auction.end_at = timezone.now() + timedelta(seconds=30)
        self.auction.save(update_fields=["end_at"])
        original_end = self.auction.end_at

        Auction.place_bid(self.auction.pk, self.buyer, Decimal("200000"))
        self.auction.refresh_from_db()

        self.assertGreater(self.auction.end_at, original_end)

    def test_early_bid_does_not_extend_deadline(self):
        original_end = self.auction.end_at

        Auction.place_bid(self.auction.pk, self.buyer, Decimal("200000"))
        self.auction.refresh_from_db()

        self.assertEqual(self.auction.end_at, original_end)

    # ------------------------------------------------------------ yakunlash

    def test_finalize_sets_winner_and_marks_product_sold(self):
        Auction.place_bid(self.auction.pk, self.buyer, Decimal("200000"))
        Auction.place_bid(self.auction.pk, self.other, Decimal("300000"))

        self.auction.end_at = timezone.now() - timedelta(seconds=1)
        self.auction.save(update_fields=["end_at"])
        self.auction.finalize()

        self.auction.refresh_from_db()
        self.product.refresh_from_db()

        self.assertEqual(self.auction.status, Auction.Status.ENDED)
        self.assertEqual(self.auction.winner, self.other)
        self.assertEqual(self.product.status, Product.Status.SOLD)

    def test_finalize_without_bids_has_no_winner(self):
        self.auction.end_at = timezone.now() - timedelta(seconds=1)
        self.auction.save(update_fields=["end_at"])
        self.auction.finalize()

        self.auction.refresh_from_db()
        self.assertEqual(self.auction.status, Auction.Status.ENDED)
        self.assertIsNone(self.auction.winner)
