from .models import BacktrackReservation


def create_backtrack_reservation(customer_name, voucher_number, room_number, check_in_date, check_out_date, confirmation_code=None, notes=''):
    if not check_in_date or not check_out_date or check_out_date <= check_in_date:
        return None

    reservation = BacktrackReservation(
        customer_name=customer_name,
        voucher_number=voucher_number or None,
        confirmation_code=confirmation_code or None,
        room_number=str(room_number),
        check_in_date=check_in_date,
        check_out_date=check_out_date,
        status='confirmed',
        notes=notes or None,
    )
    reservation.save()
    return reservation
