from django.db import models


class Room(models.Model):
    """Room model representing a lodge room."""
    room_number = models.CharField(max_length=10, unique=True)
    room_type = models.CharField(max_length=50, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['room_number']
        verbose_name = 'Room'
        verbose_name_plural = 'Rooms'

    def __str__(self):
        return f"Room {self.room_number}" + (f" ({self.room_type})" if self.room_type else "")
