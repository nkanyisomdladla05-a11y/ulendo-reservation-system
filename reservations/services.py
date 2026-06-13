import sys
from django.db import transaction
from django.db.models import Q, IntegerField
from django.db.models.functions import Cast
from datetime import date as date_type, timedelta
from .models import Reservation
from rooms.models import Room


def get_available_rooms(check_in_date, check_out_date, exclude_reservation=None):
    if not check_in_date or not check_out_date or check_out_date <= check_in_date:
        print(f"[get_available_rooms] Invalid dates: {check_in_date} - {check_out_date}", file=sys.stderr)
        return Room.objects.none()

    all_rooms = Room.objects.filter(is_active=True)
    today = date_type.today()

    booked_query = Reservation.objects.filter(
        status='confirmed',
        check_out_date__gt=today,  # ignore past bookings
    )

    if exclude_reservation:
        booked_query = booked_query.exclude(pk=exclude_reservation.pk)

    booked_room_ids = booked_query.filter(
        Q(check_in_date__lt=check_out_date) & Q(check_out_date__gt=check_in_date)
    ).values_list('room_id', flat=True).distinct()

    print(f"[get_available_rooms] dates: {check_in_date} - {check_out_date} today={today}", file=sys.stderr)
    print(f"[get_available_rooms] booked_room_ids: {list(booked_room_ids)}", file=sys.stderr)

    result = (
        all_rooms
        .exclude(id__in=booked_room_ids)
        .annotate(room_num_int=Cast('room_number', IntegerField()))
        .order_by('room_num_int')
    )
    print(f"[get_available_rooms] available rooms: {[(r.id, r.room_number) for r in result]}", file=sys.stderr)
    return result


def check_room_availability(room, check_in_date, check_out_date, exclude_reservation=None):
    if check_out_date <= check_in_date:
        return False

    today = date_type.today()
    overlapping = Reservation.objects.filter(
        room=room,
        status='confirmed',
        check_out_date__gt=today,  # ignore past bookings
    )

    if exclude_reservation:
        overlapping = overlapping.exclude(pk=exclude_reservation.pk)

    overlapping = overlapping.filter(
        Q(check_in_date__lt=check_out_date) & Q(check_out_date__gt=check_in_date)
    )

    return not overlapping.exists()


@transaction.atomic
def create_confirmed_reservation(customer_name, voucher_number, room_id, check_in_date, check_out_date, confirmation_code=None, notes='', skip_availability_check=False, exclude_reservation=None):
    """
    Single place that creates and saves a confirmed reservation. Used by both
    manual booking and voucher booking so they share the same code and logic.

    Uses select_for_update() to lock the room row during the availability check,
    preventing race conditions when two bookings happen simultaneously.

    Args:
        customer_name: Guest name
        voucher_number: Optional voucher reference
        room_id: Room primary key
        check_in_date: Check-in date object
        check_out_date: Check-out date object
        notes: Optional notes
        skip_availability_check: If True, skips the availability check
        exclude_reservation: Optional Reservation to exclude from overlap check

    Returns:
        Reservation instance, or None if room invalid or not available.
    """
    if not check_in_date or not check_out_date or check_out_date <= check_in_date:
        return None

    try:
        room = Room.objects.select_for_update().get(pk=room_id, is_active=True)
    except (Room.DoesNotExist, ValueError, TypeError):
        return None

    if not skip_availability_check and not check_room_availability(room, check_in_date, check_out_date, exclude_reservation=exclude_reservation):
        return None

    reservation = Reservation(
        customer_name=customer_name,
        voucher_number=voucher_number or None,
        confirmation_code=confirmation_code or None,
        room=room,
        check_in_date=check_in_date,
        check_out_date=check_out_date,
        status='confirmed',
        notes=notes or None,
    )
    reservation.save()
    room.update_status()
    return reservation


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
