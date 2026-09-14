from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ("id", "type", "title", "body", "link_url", "is_read", "created_at")
        read_only_fields = fields
