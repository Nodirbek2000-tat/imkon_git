from django.urls import path

from . import views

app_name = "administration"

urlpatterns = [
    path("stats/", views.StatsView.as_view(), name="stats"),

    path("users/", views.AdminUserListView.as_view(), name="users"),
    path("users/<int:pk>/toggle-admin/", views.toggle_admin, name="toggle-admin"),
    path("users/<int:pk>/toggle-active/", views.toggle_user_active, name="toggle-active"),

    path("applications/", views.ApplicationListView.as_view(), name="applications"),
    path("applications/<int:pk>/approve/", views.approve_application, name="approve"),
    path("applications/<int:pk>/reject/", views.reject_application, name="reject"),

    path("cards/", views.PaymentCardListView.as_view(), name="cards"),
    path("cards/<int:pk>/activate/", views.activate_card, name="card-activate"),
    path("cards/<int:pk>/deactivate/", views.deactivate_card, name="card-deactivate"),

    path("auctions/", views.AdminAuctionListView.as_view(), name="auctions"),
    path("auctions/create/", views.AuctionCreateView.as_view(), name="auction-create"),
    path(
        "auctions/candidates/",
        views.AuctionCandidateListView.as_view(),
        name="auction-candidates",
    ),
    path("auctions/<int:pk>/finalize/", views.finalize_auction, name="finalize"),
    path("auctions/<int:pk>/cancel/", views.cancel_auction, name="cancel"),
]
