from django.db import models
from datetime import date as date_type


class Room(models.Model):
    """Room model representing a lodge room."""
    STATUS_AVAILABLE = 'available'
    STATUS_BOOKED = 'booked'
    STATUS_CHOICES = [
        (STATUS_AVAILABLE, 'Available'),
        (STATUS_BOOKED, 'Booked'),
    ]

    room_number = models.CharField(max_length=10, unique=True)
    room_type = models.CharField(max_length=50, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_AVAILABLE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['room_number']
        verbose_name = 'Room'
        verbose_name_plural = 'Rooms'

    def __str__(self):
        return f"Room {self.room_number}" + (f" ({self.room_type})" if self.room_type else "")

    def compute_status(self):
        """Compute whether this room is currently booked or available based on today's date."""
        from reservations.models import Reservation
        today = date_type.today()
        has_active = Reservation.objects.filter(
            room=self,
            status='confirmed',
            check_in_date__lte=today,
            check_out_date__gt=today,
        ).exists()
        return self.STATUS_BOOKED if has_active else self.STATUS_AVAILABLE

    def update_status(self, save=True):
        self.status = self.compute_status()
        if save:
            self.save(update_fields=['status'])
