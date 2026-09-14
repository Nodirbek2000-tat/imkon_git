from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    path("", views.NotificationListView.as_view(), name="list"),
    path("<int:pk>/read/", views.mark_read, name="mark-read"),
    path("read-all/", views.mark_all_read, name="mark-all-read"),
]
