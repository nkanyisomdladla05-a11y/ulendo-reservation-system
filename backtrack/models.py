from django.db import models


class BacktrackReservation(models.Model):
    """Historical reservation for past dates - completely isolated from active system."""
    STATUS_CHOICES = [
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
    ]

    customer_name = models.CharField(max_length=200)
    voucher_number = models.CharField(max_length=100, blank=True, null=True)
    room_number = models.CharField(max_length=10)
    check_in_date = models.DateField()
    check_out_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='confirmed')
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-check_in_date']
        verbose_name = 'Backtrack Reservation'
        verbose_name_plural = 'Backtrack Reservations'

    def __str__(self):
        return f"{self.customer_name} - Room {self.room_number} ({self.check_in_date} to {self.check_out_date})"

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.check_out_date <= self.check_in_date:
            raise ValidationError('Check-out date must be after check-in date.')


class BacktrackVoucher(models.Model):
    """Historical voucher for OCR processing - isolated from active voucher system."""
    voucher_file = models.FileField(upload_to='backtrack_vouchers/')
    extracted_data = models.JSONField(default=dict, blank=True)
    customer_name = models.CharField(max_length=200, blank=True)
    voucher_number = models.CharField(max_length=100, blank=True)
    check_in_date = models.DateField(null=True, blank=True)
    check_out_date = models.DateField(null=True, blank=True)
    check_in_raw = models.CharField(max_length=50, blank=True)
    check_out_raw = models.CharField(max_length=50, blank=True)
    is_confirmed = models.BooleanField(default=False)
    reservation = models.ForeignKey(
        BacktrackReservation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='vouchers'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Backtrack Voucher'
        verbose_name_plural = 'Backtrack Vouchers'

    def __str__(self):
        return f"Backtrack Voucher {self.voucher_number or 'N/A'} - {self.customer_name or 'Unknown'}"
