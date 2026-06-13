import re
import calendar
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import IntegerField
from django.db.models.functions import Cast
from datetime import date, datetime, timedelta
from dateutil import parser as date_parser
from .models import Reservation
from .forms import ReservationForm
from .services import get_available_rooms, create_confirmed_reservation
from rooms.models import Room


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
def dashboard(request):
    """Dashboard view showing today's statistics."""
    today = date.today()
    total_rooms = Room.objects.filter(is_active=True).count()
    available_rooms = get_available_rooms(today, today + timedelta(days=1))
    available_count = available_rooms.count()
    check_ins = Reservation.objects.filter(check_in_date=today, status='confirmed').select_related('room').order_by('room__room_number')
    check_outs = Reservation.objects.filter(check_out_date=today, status='confirmed').select_related('room').order_by('room__room_number')
    booked_rooms = Reservation.objects.filter(check_in_date__lte=today, check_out_date__gt=today, status='confirmed').values('room').distinct().count()
    occupancy_rate = (booked_rooms / total_rooms * 100) if total_rooms > 0 else 0
    context = {'total_rooms': total_rooms, 'available_count': available_count, 'booked_count': booked_rooms, 'check_ins': check_ins, 'check_outs': check_outs, 'occupancy_rate': round(occupancy_rate, 1), 'today': today}
    return render(request, 'reservations/dashboard.html', context)


@login_required
def new_reservation(request):
    """New reservation view - handles both GET and POST requests."""
    if request.method == 'POST':
        check_in_str = request.POST.get('check_in_date', '').strip()
        check_out_str = request.POST.get('check_out_date', '').strip()
        room_id = request.POST.get('room', '').strip()

        check_in = None
        check_out = None

        if check_in_str:
            try:
                check_in = parse_date_safe(check_in_str)
            except ValueError:
                check_in = None
                messages.error(request, f'Invalid check-in date: {check_in_str}')

        if check_out_str:
            try:
                check_out = parse_date_safe(check_out_str)
            except ValueError:
                check_out = None
                messages.error(request, f'Invalid check-out date: {check_out_str}')

        dates_valid = False
        if check_in and check_out:
            if check_out > check_in:
                dates_valid = True
            else:
                messages.error(request, 'Check-out date must be after check-in date.')

        if dates_valid:
            form = ReservationForm(request.POST, check_in_date=check_in, check_out_date=check_out)
        else:
            form = ReservationForm(request.POST)

        available_rooms_count = 0
        if dates_valid and form.fields['room'].queryset:
            try:
                available_rooms_count = form.fields['room'].queryset.count()
            except Exception:
                available_rooms_count = 0

        if room_id:
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
                    messages.success(request, f'Reservation confirmed for {reservation.customer_name} in Room {reservation.room.room_number}.')
                    return redirect('reservations:dashboard')
                messages.error(request, 'Room is no longer available for the selected dates. Please choose another room.')

        context = {
            'form': form,
            'available_rooms_count': available_rooms_count,
            'check_in': check_in_str,
            'check_out': check_out_str,
        }
        return render(request, 'reservations/new_reservation.html', context)

    else:
        check_in_str = request.GET.get('check_in', '').strip()
        check_out_str = request.GET.get('check_out', '').strip()
        check_in = None
        check_out = None
        if check_in_str:
            try:
                check_in = parse_date_safe(check_in_str)
            except ValueError:
                check_in = None
        if check_out_str:
            try:
                check_out = parse_date_safe(check_out_str)
            except ValueError:
                check_out = None

        if not check_in or not check_out or check_out <= check_in:
            check_in = date.today()
            check_out = date.today() + timedelta(days=1)
            check_in_str = check_in.strftime('%Y/%m/%d')
            check_out_str = check_out.strftime('%Y/%m/%d')

        form = ReservationForm(check_in_date=check_in, check_out_date=check_out)

        return render(request, 'reservations/new_reservation.html', {
            'form': form,
            'available_rooms_count': form.fields['room'].queryset.count(),
            'check_in': check_in_str,
            'check_out': check_out_str,
        })


@login_required
def confirm_reservation(request):
    """Confirm reservation from manual form or voucher review.
    Uses the same create_confirmed_reservation() service as new_reservation
    to ensure both booking flows share identical logic.
    """
    if request.method == 'POST':
        check_in_str = request.POST.get('check_in_date', '').strip()
        check_out_str = request.POST.get('check_out_date', '').strip()
        room_id = request.POST.get('room', '').strip()

        check_in = None
        check_out = None

        if check_in_str:
            try:
                check_in = parse_date_safe(check_in_str)
            except ValueError:
                check_in = None

        if check_out_str:
            try:
                check_out = parse_date_safe(check_out_str)
            except ValueError:
                check_out = None

        dates_valid = False
        if check_in and check_out:
            if check_out > check_in:
                dates_valid = True
            else:
                messages.error(request, 'Check-out date must be after check-in date.')

        available_rooms = []
        if dates_valid:
            try:
                rooms_queryset = get_available_rooms(check_in, check_out)
                available_rooms = list(rooms_queryset) if rooms_queryset else []
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f'Error getting available rooms: {str(e)}')
                available_rooms = []
                messages.error(request, 'Error calculating available rooms. Please try again.')

        if not isinstance(available_rooms, list):
            available_rooms = list(available_rooms) if available_rooms else []

        form = ReservationForm(request.POST, check_in_date=check_in, check_out_date=check_out)

        if room_id:
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
                    messages.success(request, f'Reservation confirmed for {reservation.customer_name} in Room {reservation.room.room_number}.')
                    return redirect('reservations:dashboard')
                messages.error(request, 'Room is no longer available for the selected dates. Please choose another room.')

        context = {
            'form': form,
            'available_rooms': available_rooms,
            'check_in': check_in_str,
            'check_out': check_out_str,
        }
        return render(request, 'reservations/new_reservation.html', context)
    else:
        check_in_str = request.GET.get('check_in_date', '')
        check_out_str = request.GET.get('check_out_date', '')

        check_in = None
        check_out = None

        if check_in_str:
            try:
                check_in = parse_date_safe(check_in_str)
            except ValueError:
                check_in = None

        if check_out_str:
            try:
                check_out = parse_date_safe(check_out_str)
            except ValueError:
                check_out = None

        form = ReservationForm(check_in_date=check_in, check_out_date=check_out)
        available_rooms = []

        if check_in and check_out and check_out > check_in:
            try:
                rooms_queryset = get_available_rooms(check_in, check_out)
                available_rooms = list(rooms_queryset) if rooms_queryset else []
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f'Error getting available rooms: {str(e)}')
                available_rooms = []

        if not isinstance(available_rooms, list):
            available_rooms = list(available_rooms) if available_rooms else []

        return render(request, 'reservations/new_reservation.html', {
            'form': form,
            'available_rooms': available_rooms,
            'check_in': check_in_str if check_in_str else '',
            'check_out': check_out_str if check_out_str else '',
        })


@login_required
def room_availability(request):
    """Room-day matrix showing every room's availability per day of the month."""
    today = date.today()
    year_str = request.GET.get('year', '')
    month_str = request.GET.get('month', '')
    try:
        year = int(year_str) if year_str else today.year
        month = int(month_str) if month_str else today.month
        if month < 1 or month > 12:
            raise ValueError
    except ValueError:
        year = today.year
        month = today.month

    num_days = calendar.monthrange(year, month)[1]
    first_day = date(year, month, 1)
    last_day = date(year, month, num_days)

    rooms = Room.objects.filter(is_active=True).annotate(
        room_number_int=Cast('room_number', IntegerField())
    ).order_by('room_number_int')

    reservations = Reservation.objects.filter(
        status='confirmed',
        check_in_date__lt=last_day + timedelta(days=1),
        check_out_date__gt=first_day,
    ).select_related('room')

    # Build lookups: (room_id, day_num) -> info
    booked_lookup = {}
    checkout_lookup = {}
    for res in reservations:
        current = res.check_in_date
        while current < res.check_out_date:
            if first_day <= current <= last_day:
                booked_lookup[(res.room_id, current.day)] = {
                    'customer_name': res.customer_name,
                    'voucher_number': res.voucher_number or '',
                    'notes': res.notes or '',
                }
            current += timedelta(days=1)
        checkout_day = res.check_out_date
        if first_day <= checkout_day <= last_day:
            checkout_lookup[(res.room_id, checkout_day.day)] = {
                'customer_name': res.customer_name,
                'voucher_number': res.voucher_number or '',
                'notes': res.notes or '',
            }

    days_list = list(range(1, num_days + 1))
    weekday_abbr = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    day_weekdays = [weekday_abbr[date(year, month, d).weekday()] for d in days_list]

    rooms_data = []
    for room in rooms:
        day_cells = []
        for day_num in days_list:
            d = date(year, month, day_num)
            info = booked_lookup.get((room.id, day_num))
            checkout_info = checkout_lookup.get((room.id, day_num))
            is_checkout = checkout_info is not None and info is None
            day_cells.append({
                'day': day_num,
                'is_past': d < today,
                'is_booked': info is not None,
                'is_checkout': is_checkout,
                'customer_name': (checkout_info if is_checkout else info)['customer_name'] if info or is_checkout else '',
                'voucher_number': (checkout_info if is_checkout else info)['voucher_number'] if info or is_checkout else '',
                'notes': (checkout_info if is_checkout else info)['notes'] if info or is_checkout else '',
                'date_display': d.strftime('%a, %b %d, %Y'),
            })
        rooms_data.append({
            'room_number': room.room_number,
            'days': day_cells,
        })

    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    month_names = ['', 'January', 'February', 'March', 'April', 'May', 'June',
                   'July', 'August', 'September', 'October', 'November', 'December']

    context = {
        'year': year,
        'month': month,
        'month_name': month_names[month],
        'prev_month': prev_month,
        'prev_year': prev_year,
        'next_month': next_month,
        'next_year': next_year,
        'rooms_data': rooms_data,
        'days_list': days_list,
        'day_weekdays': day_weekdays,
        'today_day': today.day if today.month == month and today.year == year else None,
    }
    return render(request, 'reservations/room_availability.html', context)


@login_required
def api_available_rooms(request):
    """AJAX endpoint: return available rooms as JSON for given dates."""
    check_in_str = request.GET.get('check_in', '').strip()
    check_out_str = request.GET.get('check_out', '').strip()
    if not check_in_str or not check_out_str:
        return JsonResponse({'rooms': [], 'count': 0})
    try:
        check_in = parse_date_safe(check_in_str)
        check_out = parse_date_safe(check_out_str)
    except Exception:
        return JsonResponse({'rooms': [], 'count': 0})
    if not check_in or not check_out or check_out <= check_in:
        return JsonResponse({'rooms': [], 'count': 0})
    available = get_available_rooms(check_in, check_out)
    rooms = [{'id': r.room_number, 'label': str(r)} for r in available]
    return JsonResponse({'rooms': rooms, 'count': len(rooms)})


@login_required
def reservation_list(request):
    """List all reservations with search functionality."""
    reservations = Reservation.objects.select_related('room').prefetch_related('vouchers').order_by('-created_at')
    search_name = request.GET.get('name', '')
    search_voucher = request.GET.get('voucher', '')
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')
    if search_name:
        reservations = reservations.filter(customer_name__icontains=search_name)
    if search_voucher:
        reservations = reservations.filter(voucher_number__icontains=search_voucher)
    if start_date:
        try:
            start_date_obj = parse_date_safe(start_date)
            if start_date_obj:
                reservations = reservations.filter(check_in_date__gte=start_date_obj)
        except ValueError:
            pass
    if end_date:
        try:
            end_date_obj = parse_date_safe(end_date)
            if end_date_obj:
                reservations = reservations.filter(check_out_date__lte=end_date_obj)
        except ValueError:
            pass
    paginator = Paginator(reservations, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    context = {'page_obj': page_obj, 'search_name': search_name, 'search_voucher': search_voucher, 'start_date': start_date, 'end_date': end_date}
    return render(request, 'reservations/reservation_list.html', context)


@login_required
def edit_reservation(request, pk):
    """Edit an existing reservation."""
    reservation = get_object_or_404(Reservation, pk=pk)
    if request.method == 'POST':
        form = ReservationForm(request.POST, instance=reservation)
        if form.is_valid():
            updated_reservation = form.save(commit=False)
            from .services import check_room_availability
            if not check_room_availability(updated_reservation.room, updated_reservation.check_in_date, updated_reservation.check_out_date, exclude_reservation=reservation):
                messages.error(request, f'Room {updated_reservation.room.room_number} is not available for the selected dates.')
            else:
                updated_reservation.save()
                messages.success(request, 'Reservation updated successfully.')
                return redirect('reservations:reservation_list')
    else:
        form = ReservationForm(instance=reservation)
    return render(request, 'reservations/edit_reservation.html', {'form': form, 'reservation': reservation})


@login_required
def cancel_reservation(request, pk):
    """Cancel a reservation."""
    reservation = get_object_or_404(Reservation, pk=pk)
    if request.method == 'POST':
        reservation.status = 'cancelled'
        reservation.save()
        reservation.room.update_status()
        messages.success(request, f'Reservation for {reservation.customer_name} has been cancelled.')
        return redirect('reservations:reservation_list')
    return render(request, 'reservations/cancel_reservation.html', {'reservation': reservation})

@login_required
def delete_reservation(request, pk):
    """Delete a past reservation entirely."""
    reservation = get_object_or_404(Reservation, pk=pk)
    if request.method == 'POST':
        room = reservation.room
        customer = reservation.customer_name
        reservation.delete()
        room.update_status()
        messages.success(request, f'Past reservation for {customer} has been deleted.')
        return redirect('reservations:reservation_list')
    return render(request, 'reservations/delete_reservation.html', {'reservation': reservation})
