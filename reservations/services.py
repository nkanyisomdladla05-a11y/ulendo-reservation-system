from django.db.models import Q, IntegerField
from django.db.models.functions import Cast
from datetime import date, timedelta
from .models import Reservation
from rooms.models import Room


def get_rooms_available_for_booking():
    """
    Rooms that have no confirmed reservation (any date). Used for the select-room
    dropdown in both manual booking and upload voucher so the list is literally the same.
    Returns QuerySet ordered ascending by room number (1, 2, ... 30).
    """
    booked_ids = (
        Reservation.objects
        .filter(status='confirmed')
        .values_list('room_id', flat=True)
        .distinct()
    )
    return (
        Room.objects
        .filter(is_active=True)
        .exclude(id__in=booked_ids)
        .annotate(room_num_int=Cast('room_number', IntegerField()))
        .order_by('room_num_int')
    )


def create_confirmed_reservation(customer_name, voucher_number, room_id, check_in_date, check_out_date, notes='', skip_availability_check=False):
    """
    Single place that creates and saves a confirmed reservation. Used by both
    manual booking and voucher booking so they share the same code and logic.
    Accepts check_in_date and check_out_date as date objects.
    When skip_availability_check=True (e.g. after form.is_valid()), skips the
    availability check so the reservation is always created; the form already validated.
    Returns the Reservation instance, or None if room invalid or not available.
    """
    if not check_in_date or not check_out_date or check_out_date <= check_in_date:
        return None
    try:
        room = Room.objects.get(pk=room_id, is_active=True)
    except (Room.DoesNotExist, ValueError, TypeError):
        return None
    if not skip_availability_check and not check_room_availability(room, check_in_date, check_out_date):
        return None
    reservation = Reservation(
        customer_name=customer_name,
        voucher_number=voucher_number or None,
        room=room,
        check_in_date=check_in_date,
        check_out_date=check_out_date,
        status='confirmed',
        notes=notes or None,
    )
    reservation.save()
    return reservation


def check_room_availability(room, check_in_date, check_out_date, exclude_reservation=None):
    """
    Check if a room is available for the given date range.
    
    Args:
        room: Room instance
        check_in_date: Check-in date
        check_out_date: Check-out date
        exclude_reservation: Optional Reservation instance to exclude from check
    
    Returns:
        bool: True if room is available, False otherwise
    """
    # Validate dates
    if check_out_date <= check_in_date:
        return False
    
    # Query for overlapping reservations
    overlapping = Reservation.objects.filter(
        room=room,
        status='confirmed',  # Only check confirmed reservations
    )
    
    if exclude_reservation:
        overlapping = overlapping.exclude(pk=exclude_reservation.pk)
    
    overlapping = overlapping.filter(
        # Check for date overlap
        # Reservation overlaps if:
        # - check_in_date < other_check_out_date AND check_out_date > other_check_in_date
        Q(check_in_date__lt=check_out_date) & Q(check_out_date__gt=check_in_date)
    )
    
    return not overlapping.exists()


def get_available_rooms(check_in_date, check_out_date, exclude_reservation=None):
    """
    Get all available rooms for the given date range.
    
    Args:
        check_in_date: Check-in date
        check_out_date: Check-out date
        exclude_reservation: Optional Reservation instance to exclude from check
    
    Returns:
        QuerySet: Available Room instances
    """
    # Validate dates
    if check_out_date <= check_in_date:
        return Room.objects.none()
    
    # Get all active rooms
    all_rooms = Room.objects.filter(is_active=True)
    
    # Get rooms that have overlapping confirmed reservations
    booked_query = Reservation.objects.filter(
        status='confirmed',
    )
    
    if exclude_reservation:
        booked_query = booked_query.exclude(pk=exclude_reservation.pk)
    
    booked_room_ids = booked_query.filter(
        Q(check_in_date__lt=check_out_date) & Q(check_out_date__gt=check_in_date)
    ).values_list('room_id', flat=True).distinct()
    
    # Return rooms that are not booked, ordered ascending by room number (1, 2, ... 30)
    available_rooms = (
        all_rooms
        .exclude(id__in=booked_room_ids)
        .annotate(room_num_int=Cast('room_number', IntegerField()))
        .order_by('room_num_int')
    )
    return available_rooms


def get_room_status_for_date(room, target_date):
    """
    Get the status of a room for a specific date.
    
    Args:
        room: Room instance
        target_date: Date to check
    
    Returns:
        str: 'available', 'booked', or 'check_in'/'check_out' if it's a transition day
    """
    reservations = Reservation.objects.filter(
        room=room,
        status='confirmed',
        check_in_date__lte=target_date,
        check_out_date__gt=target_date
    )
    
    if reservations.exists():
        reservation = reservations.first()
        if reservation.check_in_date == target_date:
            return 'check_in'
        elif reservation.check_out_date == target_date + timedelta(days=1):
            return 'check_out'
        else:
            return 'booked'
    
    return 'available'
