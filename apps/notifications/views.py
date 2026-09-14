from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Notification
from .serializers import NotificationSerializer


class NotificationListView(ListAPIView):
    """O'z bildirishnomalari. `?unread=1` — faqat o'qilmaganlar."""

    serializer_class = NotificationSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        queryset = Notification.objects.filter(user=self.request.user)
        if self.request.query_params.get("unread") == "1":
            queryset = queryset.filter(is_read=False)
        return queryset

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        # Har javobda o'qilmagan son ham keladi — Header'dagi qo'ng'iroq
        # belgisi alohida so'rovsiz yangilanadi
        response.data["unread_count"] = Notification.objects.filter(
            user=request.user, is_read=False
        ).count()
        return response


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def mark_read(request, pk):
    updated = Notification.objects.filter(pk=pk, user=request.user).update(is_read=True)
    if not updated:
        return Response(
            {"detail": "Bildirishnoma topilmadi."}, status=status.HTTP_404_NOT_FOUND
        )
    return Response({"detail": "O'qildi."})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def mark_all_read(request):
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return Response({"detail": "Barchasi o'qildi."})
