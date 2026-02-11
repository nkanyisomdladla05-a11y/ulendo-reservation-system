from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from datetime import date, datetime, timedelta
from django.db.models import Count, Q
from reservations.models import Reservation
from rooms.models import Room
from .services import generate_pdf_report, generate_excel_report


@login_required
def daily_report(request):
    """
    Unified reports view: supports daily, weekly, monthly and custom ranges.
    
    mode:
      - daily  (default)
      - weekly (week containing the selected date, Mon–Sun)
      - monthly (calendar month of the selected date)
      - custom (explicit start_date/end_date)
    """
    mode = request.GET.get('mode', 'daily')

    # Anchor date (used for daily/weekly/monthly and as fallback for custom)
    date_str = request.GET.get('date', date.today().strftime('%Y-%m-%d'))
    try:
        anchor_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        anchor_date = date.today()

    # Determine date range
    if mode == 'weekly':
        # Week: Monday to Sunday containing the anchor_date
        start_date = anchor_date - timedelta(days=anchor_date.weekday())
        end_date = start_date + timedelta(days=6)
    elif mode == 'monthly':
        # Calendar month of the anchor_date
        start_date = anchor_date.replace(day=1)
        if start_date.month == 12:
            next_month = start_date.replace(year=start_date.year + 1, month=1, day=1)
        else:
            next_month = start_date.replace(month=start_date.month + 1, day=1)
        end_date = next_month - timedelta(days=1)
    elif mode == 'custom':
        start_str = request.GET.get('start_date')
        end_str = request.GET.get('end_date')
        try:
            start_date = datetime.strptime(start_str, '%Y-%m-%d').date() if start_str else anchor_date
        except ValueError:
            start_date = anchor_date
        try:
            end_date = datetime.strptime(end_str, '%Y-%m-%d').date() if end_str else start_date
        except ValueError:
            end_date = start_date
        # Ensure end_date is not before start_date
        if end_date < start_date:
            end_date = start_date
    else:
        # Default: single day
        mode = 'daily'
        start_date = end_date = anchor_date

    # Check-ins and check-outs within the chosen range
    check_ins = Reservation.objects.filter(
        check_in_date__gte=start_date,
        check_in_date__lte=end_date,
        status='confirmed'
    ).select_related('room').order_by('room__room_number')

    check_outs = Reservation.objects.filter(
        check_out_date__gte=start_date,
        check_out_date__lte=end_date,
        status='confirmed'
    ).select_related('room').order_by('room__room_number')

    # Occupancy over the range: rooms that are booked at any point in the window
    total_rooms = Room.objects.filter(is_active=True).count()
    overlapping_bookings = Reservation.objects.filter(
        check_in_date__lt=end_date + timedelta(days=1),
        check_out_date__gt=start_date,
        status='confirmed'
    )
    booked_rooms = overlapping_bookings.values('room').distinct().count()
    occupancy_rate = (booked_rooms / total_rooms * 100) if total_rooms > 0 else 0

    # Human‑readable date label for headings
    if start_date == end_date:
        date_label = start_date.strftime('%b %d, %Y')
    else:
        date_label = f"{start_date.strftime('%b %d, %Y')} – {end_date.strftime('%b %d, %Y')}"

    export_format = request.GET.get('export')
    # For exports we keep using the daily layout and pass a string label
    export_label = date_label
    export_payload = {
        'mode': mode,
        'date_label': date_label,
        'check_ins': check_ins,
        'check_outs': check_outs,
        'occupancy_rate': occupancy_rate,
        'total_rooms': total_rooms,
        'booked_rooms': booked_rooms,
    }
    if export_format == 'pdf':
        return generate_pdf_report('daily', export_label, export_payload)
    elif export_format == 'excel':
        return generate_excel_report('daily', export_label, export_payload)

    context = {
        'mode': mode,
        'anchor_date': anchor_date,
        'start_date': start_date,
        'end_date': end_date,
        'date_label': date_label,
        'check_ins': check_ins,
        'check_outs': check_outs,
        'occupancy_rate': round(occupancy_rate, 1),
        'total_rooms': total_rooms,
        'booked_rooms': booked_rooms,
    }

    return render(request, 'reports/daily_report.html', context)


@login_required
def monthly_report(request):
    """Monthly summary report."""
    month = request.GET.get('month', date.today().strftime('%Y-%m'))
    
    try:
        year, month_num = map(int, month.split('-'))
        start_date = date(year, month_num, 1)
        if month_num == 12:
            end_date = date(year + 1, 1, 1)
        else:
            end_date = date(year, month_num + 1, 1)
    except ValueError:
        start_date = date.today().replace(day=1)
        if start_date.month == 12:
            end_date = start_date.replace(year=start_date.year + 1, month=1)
        else:
            end_date = start_date.replace(month=start_date.month + 1)
    
    # Get reservations in the month
    reservations = Reservation.objects.filter(
        check_in_date__gte=start_date,
        check_in_date__lt=end_date,
        status='confirmed'
    ).select_related('room')
    
    total_bookings = reservations.count()
    
    # Calculate daily occupancy rates
    daily_stats = []
    current_date = start_date
    total_rooms = Room.objects.filter(is_active=True).count()
    
    while current_date < end_date:
        booked = Reservation.objects.filter(
            check_in_date__lte=current_date,
            check_out_date__gt=current_date,
            status='confirmed'
        ).values('room').distinct().count()
        
        occupancy = (booked / total_rooms * 100) if total_rooms > 0 else 0
        daily_stats.append({
            'date': current_date,
            'booked': booked,
            'occupancy': round(occupancy, 1),
        })
        current_date += timedelta(days=1)
    
    avg_occupancy = sum(s['occupancy'] for s in daily_stats) / len(daily_stats) if daily_stats else 0
    
    export_format = request.GET.get('export')
    if export_format == 'pdf':
        return generate_pdf_report('monthly', start_date, {
            'reservations': reservations,
            'total_bookings': total_bookings,
            'daily_stats': daily_stats,
            'avg_occupancy': avg_occupancy,
            'total_rooms': total_rooms,
        })
    elif export_format == 'excel':
        return generate_excel_report('monthly', start_date, {
            'reservations': reservations,
            'total_bookings': total_bookings,
            'daily_stats': daily_stats,
            'avg_occupancy': avg_occupancy,
            'total_rooms': total_rooms,
        })
    
    context = {
        'month': month,
        'start_date': start_date,
        'end_date': end_date,
        'reservations': reservations[:50],  # Limit for display
        'total_bookings': total_bookings,
        'daily_stats': daily_stats,
        'avg_occupancy': round(avg_occupancy, 1),
        'total_rooms': total_rooms,
    }
    
    return render(request, 'reports/monthly_report.html', context)


@login_required
def occupancy_report(request):
    """Occupancy rate report for a specific date."""
    report_date = request.GET.get('date', date.today().strftime('%Y-%m-%d'))
    
    try:
        report_date = datetime.strptime(report_date, '%Y-%m-%d').date()
    except ValueError:
        report_date = date.today()
    
    total_rooms = Room.objects.filter(is_active=True).count()
    booked_rooms = Reservation.objects.filter(
        check_in_date__lte=report_date,
        check_out_date__gt=report_date,
        status='confirmed'
    ).values('room').distinct().count()
    
    available_rooms = total_rooms - booked_rooms
    occupancy_rate = (booked_rooms / total_rooms * 100) if total_rooms > 0 else 0
    
    # Get room details
    booked_reservations = Reservation.objects.filter(
        check_in_date__lte=report_date,
        check_out_date__gt=report_date,
        status='confirmed'
    ).select_related('room', 'room__room_type').order_by('room__room_number')
    
    context = {
        'report_date': report_date,
        'total_rooms': total_rooms,
        'booked_rooms': booked_rooms,
        'available_rooms': available_rooms,
        'occupancy_rate': round(occupancy_rate, 1),
        'booked_reservations': booked_reservations,
    }
    
    return render(request, 'reports/occupancy_report.html', context)
