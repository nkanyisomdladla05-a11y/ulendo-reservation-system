from django.db import models
from reservations.models import Reservation


class Voucher(models.Model):
    """Voucher model for storing uploaded vouchers and OCR extracted data."""
    voucher_file = models.FileField(upload_to='vouchers/')
    extracted_data = models.JSONField(default=dict, blank=True)
    customer_name = models.CharField(max_length=200, blank=True)
    voucher_number = models.CharField(max_length=100, blank=True)
    check_in_date = models.DateField(null=True, blank=True)
    check_out_date = models.DateField(null=True, blank=True)
    is_confirmed = models.BooleanField(default=False)
    reservation = models.ForeignKey(
        Reservation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='vouchers'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Voucher'
        verbose_name_plural = 'Vouchers'

    def __str__(self):
        return f"Voucher {self.voucher_number or 'N/A'} - {self.customer_name or 'Unknown'}"
