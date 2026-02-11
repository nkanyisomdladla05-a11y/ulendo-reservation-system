import logging

from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from datetime import date, datetime
from .models import Voucher
from .forms import VoucherUploadForm, VoucherReviewForm
from .services import extract_voucher_data
from reservations.models import Reservation
from reservations.services import get_rooms_available_for_booking, create_confirmed_reservation
from reservations.forms import ReservationForm

logger = logging.getLogger(__name__)


@login_required
def upload_voucher(request):
    """Upload voucher and extract data using OCR."""
    if request.method == 'POST':
        form = VoucherUploadForm(request.POST, request.FILES)
        if form.is_valid():
            # Save voucher first so the uploaded file is written to disk (with
            # save(commit=False) the file is not yet in MEDIA_ROOT).
            voucher = form.save()
            try:
                extracted = extract_voucher_data(voucher.voucher_file.path)

                # Prepare JSON-serializable copy of extracted data for JSONField
                extracted_json = extracted.copy() if isinstance(extracted, dict) else {}
                ci = extracted_json.get('check_in_date')
                co = extracted_json.get('check_out_date')
                if isinstance(ci, date):
                    extracted_json['check_in_date'] = ci.isoformat()
                if isinstance(co, date):
                    extracted_json['check_out_date'] = co.isoformat()

                voucher.extracted_data = extracted_json
                voucher.customer_name = extracted.get('customer_name', '')
                voucher.voucher_number = extracted.get('voucher_number', '')
                voucher.check_in_date = extracted.get('check_in_date')
                voucher.check_out_date = extracted.get('check_out_date')
                voucher.save(update_fields=[
                    'extracted_data', 'customer_name', 'voucher_number',
                    'check_in_date', 'check_out_date'
                ])
                return redirect('vouchers:review_voucher', voucher_id=voucher.id)
            except Exception as e:
                voucher.delete()  # Remove voucher so user can re-upload
                messages.error(request, f'Error processing voucher: {str(e)}')
                return render(request, 'vouchers/upload_voucher.html', {'form': form})
    else:
        form = VoucherUploadForm()
    
    return render(request, 'vouchers/upload_voucher.html', {'form': form})


@login_required
def review_voucher(request, voucher_id):
    """Review and edit OCR extracted data, then confirm reservation.
    Room dropdown is the same as manual booking: get_rooms_available_for_booking() so the list is literally the same.
    Voucher linking is deferred via on_commit so the reservation persists before any further work.
    """
    voucher = get_object_or_404(Voucher, pk=voucher_id)
    
    if request.method == 'POST':
        # Prevent double-booking: if this voucher already has a confirmed reservation, do not create another
        if getattr(voucher, 'reservation_id', None) and voucher.is_confirmed:
            messages.info(request, 'This voucher is already confirmed.')
            return redirect('reservations:dashboard')
        
        # Update voucher with edited data
        voucher.customer_name = request.POST.get('customer_name', '')
        voucher.voucher_number = request.POST.get('voucher_number', '')
        
        # Parse POST dates robustly: only catch ValueError, always store date objects or None
        check_in_str = request.POST.get('check_in_date', '').strip()
        check_out_str = request.POST.get('check_out_date', '').strip()
        voucher.check_in_date = None
        voucher.check_out_date = None
        if check_in_str:
            try:
                voucher.check_in_date = datetime.strptime(check_in_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        if check_out_str:
            try:
                voucher.check_out_date = datetime.strptime(check_out_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        voucher.save()
        
        # Build form_data and create reservation only when we have valid date objects
        room_id = request.POST.get('room')
        has_valid_dates = (
            isinstance(voucher.check_in_date, date)
            and isinstance(voucher.check_out_date, date)
            and voucher.check_out_date > voucher.check_in_date
        )
        if room_id and has_valid_dates:
            form_data = {
                'customer_name': voucher.customer_name,
                'voucher_number': voucher.voucher_number or '',
                'room': room_id,
                'check_in_date': voucher.check_in_date.strftime('%Y-%m-%d'),
                'check_out_date': voucher.check_out_date.strftime('%Y-%m-%d'),
                'notes': '',
            }
            form = ReservationForm(
                form_data,
                check_in_date=voucher.check_in_date,
                check_out_date=voucher.check_out_date,
            )
            if form.is_valid():
                cd = form.cleaned_data
                reservation = create_confirmed_reservation(
                    customer_name=cd['customer_name'],
                    voucher_number=cd.get('voucher_number') or '',
                    room_id=cd['room'].id,
                    check_in_date=cd['check_in_date'],
                    check_out_date=cd['check_out_date'],
                    notes=cd.get('notes') or '',
                    skip_availability_check=True,
                )
                if reservation:
                    def link_voucher():
                        try:
                            voucher.reservation = reservation
                            voucher.is_confirmed = True
                            voucher.save(update_fields=['reservation', 'is_confirmed'])
                        except Exception:
                            logger.exception("Failed to link voucher to reservation")
                    transaction.on_commit(link_voucher)
                    messages.success(request, f'Reservation confirmed for {reservation.customer_name} in Room {reservation.room.room_number}.')
                    availability_url = reverse('reservations:room_availability')
                    availability_url += f'?start_date={reservation.check_in_date.isoformat()}&end_date={reservation.check_out_date.isoformat()}'
                    return redirect(availability_url)
                messages.error(request, 'Room is no longer available for the selected dates. Please choose another room.')
            else:
                for _field, errors in form.errors.items():
                    for msg in errors:
                        messages.error(request, msg)
        elif not has_valid_dates and (check_in_str or check_out_str):
            messages.error(request, 'Please set valid check-in and check-out dates.')
        else:
            messages.error(request, 'Please select a room and ensure dates are set.')
    
    # Same room list as manual booking: get_rooms_available_for_booking() so dropdown is literally the same.
    available_rooms = []
    if voucher.check_in_date and voucher.check_out_date and voucher.check_out_date > voucher.check_in_date:
        available_rooms = list(get_rooms_available_for_booking())
    
    context = {
        'voucher': voucher,
        'available_rooms': available_rooms,
    }
    
    return render(request, 'vouchers/review_voucher.html', context)
