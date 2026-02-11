from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import IntegerField
from django.db.models.functions import Cast
from datetime import date, datetime, timedelta
from .models import Reservation
from .forms import ReservationForm
from .services import get_available_rooms, create_confirmed_reservation
from rooms.models import Room


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
        # Handle form submission
        check_in_str = request.POST.get('check_in_date', '').strip()
        check_out_str = request.POST.get('check_out_date', '').strip()
        room_id = request.POST.get('room', '').strip()
        
        # Parse dates with explicit error handling
        check_in = None
        check_out = None
        
        if check_in_str:
            try:
                check_in = datetime.strptime(check_in_str, '%Y-%m-%d').date()
            except ValueError:
                check_in = None
                messages.error(request, f'Invalid check-in date: {check_in_str}')
        
        if check_out_str:
            try:
                check_out = datetime.strptime(check_out_str, '%Y-%m-%d').date()
            except ValueError:
                check_out = None
                messages.error(request, f'Invalid check-out date: {check_out_str}')
        
        # Validate dates are valid and check-out is after check-in
        dates_valid = False
        if check_in and check_out:
            if check_out > check_in:
                dates_valid = True
            else:
                messages.error(request, 'Check-out date must be after check-in date.')
        
        # Create form with POST data and parsed dates
        # Only pass dates to form if they're valid (form will filter rooms automatically)
        if dates_valid:
            form = ReservationForm(request.POST, check_in_date=check_in, check_out_date=check_out)
        else:
            # Dates invalid or missing - form will show all active rooms
            form = ReservationForm(request.POST)
        
        # Get available rooms count for display messages (form already has filtered queryset)
        available_rooms_count = 0
        if dates_valid and form.fields['room'].queryset:
            try:
                available_rooms_count = form.fields['room'].queryset.count()
            except Exception:
                available_rooms_count = 0
        
        # If room is selected, validate and create via shared service (same as voucher booking)
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
        
        # No room selected or form has errors - show form with available rooms
        context = {
            'form': form,
            'available_rooms_count': available_rooms_count,
            'check_in': check_in_str,
            'check_out': check_out_str,
        }
        return render(request, 'reservations/new_reservation.html', context)
    
    else:
        # GET request - show empty form
        form = ReservationForm()
        return render(request, 'reservations/new_reservation.html', {
            'form': form,
            'available_rooms_count': 0,
            'check_in': '',
            'check_out': '',
        })


@login_required
def confirm_reservation(request):
    """Confirm reservation from manual form or voucher review."""
    if request.method == 'POST':
        # Get raw POST data first
        check_in_str = request.POST.get('check_in_date', '').strip()
        check_out_str = request.POST.get('check_out_date', '').strip()
        room_id = request.POST.get('room', '').strip()
        
        # Debug: Store POST data for template debugging
        post_data_debug = {
            'check_in_date_raw': request.POST.get('check_in_date', 'NOT_FOUND'),
            'check_out_date_raw': request.POST.get('check_out_date', 'NOT_FOUND'),
            'room_raw': request.POST.get('room', 'NOT_FOUND'),
            'check_in_str': check_in_str,
            'check_out_str': check_out_str,
        }
        
        # Parse dates with explicit error handling
        check_in = None
        check_out = None
        date_parse_errors = []
        
        if check_in_str:
            try:
                check_in = datetime.strptime(check_in_str, '%Y-%m-%d').date()
            except ValueError:
                date_parse_errors.append(f'Invalid check-in date: {check_in_str}')
                check_in = None
        
        if check_out_str:
            try:
                check_out = datetime.strptime(check_out_str, '%Y-%m-%d').date()
            except ValueError:
                date_parse_errors.append(f'Invalid check-out date: {check_out_str}')
                check_out = None
        
        # Validate dates are valid and check-out is after check-in
        dates_valid = False
        if check_in and check_out:
            if check_out > check_in:
                dates_valid = True
            else:
                messages.error(request, 'Check-out date must be after check-in date.')
        
        # ALWAYS get available rooms if dates are valid
        available_rooms = []
        if dates_valid:
            try:
                rooms_queryset = get_available_rooms(check_in, check_out)
                available_rooms = list(rooms_queryset) if rooms_queryset else []
            except Exception as e:
                # Log the error but don't break the flow
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f'Error getting available rooms: {str(e)}')
                available_rooms = []
                messages.error(request, 'Error calculating available rooms. Please try again.')
        else:
            # Dates not valid, ensure empty list
            available_rooms = []
        
        # Ensure available_rooms is always a list (never None)
        if not isinstance(available_rooms, list):
            available_rooms = list(available_rooms) if available_rooms else []
        
        # Create form with POST data and parsed dates
        form = ReservationForm(request.POST, check_in_date=check_in, check_out_date=check_out)
        
        # If room is selected, try to save
        if room_id:
            if form.is_valid():
                reservation = form.save(commit=False)
                reservation.status = 'confirmed'
                reservation.save()
                messages.success(request, f'Reservation confirmed for {reservation.customer_name} in Room {reservation.room.room_number}.')
                return redirect('reservations:dashboard')
        
        # Always render the form with available rooms (whether room selected or not)
        # Use the string values from POST for template display
        context = {
            'form': form,
            'available_rooms': available_rooms,
            'check_in': check_in_str,
            'check_out': check_out_str,
            'post_debug': post_data_debug,  # Debug info
        }
        return render(request, 'reservations/new_reservation.html', context)
    else:
        # GET request - initial form load
        check_in_str = request.GET.get('check_in_date', '')
        check_out_str = request.GET.get('check_out_date', '')
        
        check_in = None
        check_out = None
        
        if check_in_str:
            try:
                check_in = datetime.strptime(check_in_str, '%Y-%m-%d').date()
            except ValueError:
                check_in = None
        
        if check_out_str:
            try:
                check_out = datetime.strptime(check_out_str, '%Y-%m-%d').date()
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
        
        # Ensure it's always a list
        if not isinstance(available_rooms, list):
            available_rooms = list(available_rooms) if available_rooms else []
        
        return render(request, 'reservations/new_reservation.html', {
            'form': form,
            'available_rooms': available_rooms,
            'check_in': check_in_str if check_in_str else '',
            'check_out': check_out_str if check_out_str else '',
            'post_debug': None,  # No POST data on GET request
        })


@login_required
def room_availability(request):
    """Room availability view with date range filtering."""
    today = date.today()
    start_date = request.GET.get('start_date', today.strftime('%Y-%m-%d'))
    end_date = request.GET.get('end_date', (today + timedelta(days=7)).strftime('%Y-%m-%d'))
    try:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    except ValueError:
        start_date = today
        end_date = today + timedelta(days=7)
    if end_date < start_date:
        end_date = start_date + timedelta(days=7)
    # Order rooms numerically by room_number (stored as string) so
    # Room 1 .. Room 30 appear in ascending order.
    rooms = Room.objects.filter(is_active=True).annotate(
        room_num_int=Cast('room_number', IntegerField())
    ).order_by('room_num_int')
    # Only confirmed reservations count as booked; cancelled rooms reappear as available.
    reservations = Reservation.objects.filter(status='confirmed', check_in_date__lt=end_date, check_out_date__gt=start_date).select_related('room')
    room_statuses = []
    for room in rooms:
        room_reservations = [r for r in reservations if r.room_id == room.id]
        status = 'available' if not room_reservations else 'booked'
        room_statuses.append({'room': room, 'status': status, 'reservations': room_reservations})
    context = {'rooms': room_statuses, 'start_date': start_date, 'end_date': end_date}
    return render(request, 'reservations/room_availability.html', context)


@login_required
def reservation_list(request):
    """List all reservations with search functionality."""
    reservations = Reservation.objects.select_related('room').order_by('-created_at')
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
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
            reservations = reservations.filter(check_in_date__gte=start_date_obj)
        except ValueError:
            pass
    if end_date:
        try:
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
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
        messages.success(request, f'Reservation for {reservation.customer_name} has been cancelled.')
        return redirect('reservations:reservation_list')
    return render(request, 'reservations/cancel_reservation.html', {'reservation': reservation})
