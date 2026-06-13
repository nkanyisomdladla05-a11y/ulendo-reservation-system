import logging
import re

from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from datetime import date, datetime, timedelta
from dateutil import parser as date_parser
from .models import Voucher
from .forms import VoucherUploadForm, VoucherReviewForm
from .services import extract_voucher_data
from reservations.models import Reservation
from reservations.services import create_confirmed_reservation
from reservations.forms import ReservationForm
from rooms.models import Room

logger = logging.getLogger(__name__)


def parse_date_safe(date_str):
    """Parse date string safely, handling YYYY/MM/DD and YY/MM/DD formats correctly."""
    if not date_str:
        return None
    date_str = date_str.strip()
    ymd = re.match(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', date_str)
    if ymd:
        try:
            return date(int(ymd.group(1)), int(ymd.group(2)), int(ymd.group(3)))
        except ValueError:
            return None
    dmy = re.match(r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})', date_str)
    if dmy:
        try:
            return date(int(dmy.group(3)), int(dmy.group(2)), int(dmy.group(1)))
        except ValueError:
            return None
    ymd2 = re.match(r'(\d{2})[/-](\d{1,2})[/-](\d{2})$', date_str)
    if ymd2:
        try:
            year = int(ymd2.group(1))
            year = year + 2000 if year < 100 else year
            return date(year, int(ymd2.group(2)), int(ymd2.group(3)))
        except ValueError:
            return None
    try:
        return date_parser.parse(date_str, dayfirst=True).date()
    except ValueError:
        return None


@login_required
def upload_voucher(request):
    """Upload voucher and extract data using OCR."""
    if request.method == 'POST':
        form = VoucherUploadForm(request.POST, request.FILES)
        manual_check_in = request.POST.get('check_in_date', '').strip()
        manual_check_out = request.POST.get('check_out_date', '').strip()
        if form.is_valid():
            voucher = form.save()
            try:
                extracted = extract_voucher_data(voucher.voucher_file.path)

                extracted_json = extracted.copy() if isinstance(extracted, dict) else {}
                ci = extracted_json.get('check_in_date')
                co = extracted_json.get('check_out_date')
                if isinstance(ci, date):
                    extracted_json['check_in_date'] = ci.strftime('%Y/%m/%d')
                if isinstance(co, date):
                    extracted_json['check_out_date'] = co.strftime('%Y/%m/%d')

                voucher.extracted_data = extracted_json
                voucher.customer_name = extracted.get('customer_name', '')
                voucher.voucher_number = extracted.get('voucher_number', '')
                voucher.check_in_date = extracted.get('check_in_date')
                voucher.check_out_date = extracted.get('check_out_date')
                voucher.save(update_fields=[
                    'extracted_data', 'customer_name', 'voucher_number',
                    'check_in_date', 'check_out_date'
                ])

                # Debug log
                import sys
                print(f"\n=== VOUCHER SAVED ===", file=sys.stderr)
                print(f"Saved check_in: {voucher.check_in_date}", file=sys.stderr)
                print(f"Saved check_out: {voucher.check_out_date}", file=sys.stderr)
                print(f"Saved extracted_data: {dict(voucher.extracted_data)}", file=sys.stderr)
                print(f"=====================\n", file=sys.stderr)

                review_url = reverse('vouchers:review_voucher', kwargs={'voucher_id': voucher.id})
                params = []
                if manual_check_in:
                    params.append(f'check_in={manual_check_in}')
                if manual_check_out:
                    params.append(f'check_out={manual_check_out}')
                if params:
                    review_url += '?' + '&'.join(params)
                return redirect(review_url)
            except Exception as e:
                voucher.delete()
                messages.error(request, f'Error processing voucher: {str(e)}')
                return render(request, 'vouchers/upload_voucher.html', {'form': form})
    else:
        form = VoucherUploadForm()

    return render(request, 'vouchers/upload_voucher.html', {'form': form})


@login_required
def review_voucher(request, voucher_id):
    """Review and edit OCR extracted data, then confirm reservation.
    Uses ReservationForm for the room dropdown, identical to manual booking.
    Reservation creation uses create_confirmed_reservation() for shared logic
    and race-condition protection.
    Voucher linking is deferred via on_commit so the reservation persists before any further work.
    """
    voucher = get_object_or_404(Voucher, pk=voucher_id)

    if request.method == 'POST':
        if getattr(voucher, 'reservation_id', None) and voucher.is_confirmed:
            messages.info(request, 'This voucher is already confirmed.')
            return redirect('reservations:dashboard')

        voucher.customer_name = request.POST.get('customer_name', '')
        voucher.voucher_number = request.POST.get('voucher_number', '')

        check_in_str = request.POST.get('check_in_date', '').strip()
        check_out_str = request.POST.get('check_out_date', '').strip()
        voucher.check_in_date = None
        voucher.check_out_date = None
        if check_in_str:
            try:
                voucher.check_in_date = parse_date_safe(check_in_str)
            except ValueError:
                pass
        if check_out_str:
            try:
                voucher.check_out_date = parse_date_safe(check_out_str)
            except ValueError:
                pass
        voucher.save()

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
                'confirmation_code': request.POST.get('confirmation_code', ''),
                'room': room_id,
                'check_in_date': voucher.check_in_date.strftime('%Y/%m/%d'),
                'check_out_date': voucher.check_out_date.strftime('%Y/%m/%d'),
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
                    confirmation_code=cd.get('confirmation_code') or '',
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
                    availability_url += f'?start_date={reservation.check_in_date.strftime("%Y/%m/%d")}&end_date={reservation.check_out_date.strftime("%Y/%m/%d")}'
                    return redirect(availability_url)
                messages.error(request, 'Room is no longer available for the selected dates. Please choose another room.')
            else:
                for _field, errors in form.errors.items():
                    for msg in errors:
                        messages.error(request, msg)

                # Rebuild room field queryset to show all rooms with status (unfiltered by dates)
                from datetime import date as dt_date
                from django.db.models import Exists, OuterRef, IntegerField
                from django.db.models.functions import Cast
                today = dt_date.today()
                all_rooms = Room.objects.filter(is_active=True).annotate(
                    has_booking=Exists(
                        Reservation.objects.filter(
                            room=OuterRef('pk'),
                            status='confirmed',
                            check_out_date__gt=today,
                        )
                    ),
                    room_num_int=Cast('room_number', IntegerField())
                ).order_by('room_num_int')
                form.fields['room'].queryset = all_rooms

                def label_from_instance(room):
                    label = f"Room {room.room_number}"
                    if room.room_type:
                        label += f" ({room.room_type})"
                    if getattr(room, 'has_booking', False):
                        label += " — Booked"
                    if room.status == 'booked':
                        label += " ●"
                    return label
                form.fields['room'].label_from_instance = label_from_instance

                form_room = form.fields['room'].queryset
                available_rooms_count = form_room.filter(status='available').count() if form_room else 0
                context = {
                    'voucher': voucher,
                    'form': form,
                    'available_rooms_count': available_rooms_count,
                }
                return render(request, 'vouchers/review_voucher.html', context)
        elif not has_valid_dates and (check_in_str or check_out_str):
            messages.error(request, 'Please set valid check-in and check-out dates.')
        else:
            messages.error(request, 'Please select a room and ensure dates are set.')

    form_check_in = voucher.check_in_date
    form_check_out = voucher.check_out_date

    # Filter room dropdown by current availability (today's date), like manual booking
    today = date.today()
    tomorrow = today + timedelta(days=1)
    form = ReservationForm(check_in_date=today, check_out_date=tomorrow)
    available_rooms_count = form.fields['room'].queryset.count()

    context = {
        'voucher': voucher,
        'form': form,
        'available_rooms_count': available_rooms_count,
        'check_in': form_check_in.strftime('%Y/%m/%d') if form_check_in else '',
        'check_out': form_check_out.strftime('%Y/%m/%d') if form_check_out else '',
    }

    # Debug log
    import sys
    print(f"\n=== REVIEW PAGE ===", file=sys.stderr)
    print(f"form_check_in: {form_check_in} form_check_out: {form_check_out}", file=sys.stderr)
    print(f"context check_in: '{context['check_in']}' check_out: '{context['check_out']}'", file=sys.stderr)
    print(f"voucher.check_in_date: {voucher.check_in_date}", file=sys.stderr)
    print(f"voucher.check_out_date: {voucher.check_out_date}", file=sys.stderr)
    print(f"voucher.extracted_data: {dict(voucher.extracted_data) if voucher.extracted_data else None}", file=sys.stderr)
    print(f"==================\n", file=sys.stderr)

    return render(request, 'vouchers/review_voucher.html', context)
