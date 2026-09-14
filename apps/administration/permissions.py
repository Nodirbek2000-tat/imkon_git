from rest_framework import permissions


class IsPlatformAdmin(permissions.BasePermission):
    """
    Admin panelga kirish.

    Django'ning `is_staff` bayrog'idan foydalanamiz — shu bilan bitta odam
    ham admin, ham hunarmand bo'la oladi (`role` bozordagi maqom, `is_staff`
    boshqaruv huquqi). Ikkalasini bitta maydonga tiqish keyin cheklov bo'lardi.
    """

    message = "Bu bo'lim faqat adminlar uchun."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_staff)
