from django.db import models
from django.core.validators import MinValueValidator
from rooms.models import Room


class Reservation(models.Model):
    """Reservation model representing a room booking."""
    STATUS_CHOICES = [
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
    ]

    customer_name = models.CharField(max_length=200)
    voucher_number = models.CharField(max_length=100, blank=True, null=True)
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='reservations')
    check_in_date = models.DateField()
    check_out_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='confirmed')
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Reservation'
        verbose_name_plural = 'Reservations'
        indexes = [
            models.Index(fields=['check_in_date', 'check_out_date']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.customer_name} - Room {self.room.room_number} ({self.check_in_date} to {self.check_out_date})"

    def clean(self):
        """Validate that check-out date is after check-in date."""
        from django.core.exceptions import ValidationError
        if self.check_out_date <= self.check_in_date:
            raise ValidationError('Check-out date must be after check-in date.')
