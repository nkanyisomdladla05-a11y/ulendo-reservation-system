from .models import BacktrackReservation


def create_backtrack_reservation(customer_name, voucher_number, room_number, check_in_date, check_out_date, notes=''):
    """
    Create a backtrack reservation WITHOUT availability checks.
    Used for historical/past date reservations.
    """
    if not check_in_date or not check_out_date or check_out_date <= check_in_date:
        return None

    reservation = BacktrackReservation(
        customer_name=customer_name,
        voucher_number=voucher_number or None,
        room_number=str(room_number),
        check_in_date=check_in_date,
        check_out_date=check_out_date,
        status='confirmed',
        notes=notes or None,
    )
    reservation.save()
    return reservation
