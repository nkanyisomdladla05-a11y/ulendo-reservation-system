from django.contrib import admin
from .models import BacktrackReservation, BacktrackVoucher


@admin.register(BacktrackReservation)
class BacktrackReservationAdmin(admin.ModelAdmin):
    list_display = ('customer_name', 'room_number', 'check_in_date', 'check_out_date', 'status')
    list_filter = ('status',)
    search_fields = ('customer_name', 'voucher_number')


@admin.register(BacktrackVoucher)
class BacktrackVoucherAdmin(admin.ModelAdmin):
    list_display = ('voucher_number', 'customer_name', 'check_in_date', 'is_confirmed')
    list_filter = ('is_confirmed',)
    search_fields = ('customer_name', 'voucher_number')
