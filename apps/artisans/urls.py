from django.urls import path

from .views import (
    ApplicationView,
    CraftListView,
    MyShopView,
    MySchoolView,
    SchoolStudentDetailView,
    SchoolStudentListView,
)

app_name = "artisans"

urlpatterns = [
    path("crafts/", CraftListView.as_view(), name="crafts"),
    path("shop/apply/", ApplicationView.as_view(), name="apply"),
    path("shop/me/", MyShopView.as_view(), name="my-shop"),

    # Maktabning o'z bo'limi. `school/` (birlikda) — ommaviy `schools/`
    # router'i bilan to'qnashmasligi uchun: `schools/me/` bo'lsa "me"
    # maktab slug'i deb qabul qilinardi.
    path("school/me/", MySchoolView.as_view(), name="my-school"),
    path("school/students/", SchoolStudentListView.as_view(), name="school-students"),
    path(
        "school/students/<slug:slug>/",
        SchoolStudentDetailView.as_view(),
        name="school-student",
    ),
]
