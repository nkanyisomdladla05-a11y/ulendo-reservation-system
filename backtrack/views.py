import logging
import re

from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import HttpResponse
from datetime import date, datetime, timedelta
from dateutil import parser as date_parser

from .models import BacktrackReservation, BacktrackVoucher
from .forms import BacktrackReservationForm, BacktrackVoucherUploadForm
from .services import create_backtrack_reservation
from vouchers.services import extract_voucher_data

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
def dashboard(request):
    """Backtrack dashboard showing historical reservation stats."""
    today = date.today()
    total = BacktrackReservation.objects.count()
    confirmed = BacktrackReservation.objects.filter(status='confirmed').count()
    cancelled = BacktrackReservation.objects.filter(status='cancelled').count()
    recent = BacktrackReservation.objects.order_by('-created_at')[:10]

    context = {
        'total': total,
        'confirmed': confirmed,
        'cancelled': cancelled,
        'recent': recent,
        'today': today,
    }
    return render(request, 'backtrack/dashboard.html', context)


@login_required
def new_backtrack(request):
    """New backtrack reservation - manual booking for past dates."""
    if request.method == 'POST':
        check_in_str = request.POST.get('check_in_date', '').strip()
        check_out_str = request.POST.get('check_out_date', '').strip()
        room_number = request.POST.get('room_number', '').strip()

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
            form = BacktrackReservationForm(request.POST)
        else:
            form = BacktrackReservationForm(request.POST)

        if room_number and form.is_valid():
            cd = form.cleaned_data
            reservation = create_backtrack_reservation(
                customer_name=cd['customer_name'],
                voucher_number=cd.get('voucher_number') or '',
                room_number=cd['room_number'],
                check_in_date=cd['check_in_date'],
                check_out_date=cd['check_out_date'],
                notes=cd.get('notes') or '',
            )
            if reservation:
                messages.success(request, f'Backtrack reservation confirmed for {reservation.customer_name} in Room {reservation.room_number}.')
                return redirect('backtrack:dashboard')
            messages.error(request, 'Could not create backtrack reservation. Please check your data.')

        context = {
            'form': form,
            'check_in': check_in_str,
            'check_out': check_out_str,
        }
        return render(request, 'backtrack/new_backtrack.html', context)

    else:
        form = BacktrackReservationForm()
        return render(request, 'backtrack/new_backtrack.html', {
            'form': form,
            'check_in': '',
            'check_out': '',
        })


@login_required
def upload_backtrack_voucher(request):
    """Upload voucher for backtrack processing."""
    if request.method == 'POST':
        form = BacktrackVoucherUploadForm(request.POST, request.FILES)
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
                voucher.check_in_raw = extracted.get('check_in_raw', '')
                voucher.check_out_raw = extracted.get('check_out_raw', '')
                voucher.save(update_fields=[
                    'extracted_data', 'customer_name', 'voucher_number',
                    'check_in_date', 'check_out_date', 'check_in_raw', 'check_out_raw'
                ])
                return redirect('backtrack:review_backtrack_voucher', voucher_id=voucher.id)
            except Exception as e:
                voucher.delete()
                messages.error(request, f'Error processing voucher: {str(e)}')
                return render(request, 'backtrack/new_backtrack.html', {'upload_form': form})
    else:
        form = BacktrackVoucherUploadForm()

    return render(request, 'backtrack/new_backtrack.html', {'upload_form': form})


@login_required
def review_backtrack_voucher(request, voucher_id):
    """Review OCR extracted data for backtrack voucher and confirm reservation."""
    voucher = get_object_or_404(BacktrackVoucher, pk=voucher_id)

    if request.method == 'POST':
        if getattr(voucher, 'reservation_id', None) and voucher.is_confirmed:
            messages.info(request, 'This voucher is already confirmed.')
            return redirect('backtrack:dashboard')

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

        room_number = request.POST.get('room_number')
        has_valid_dates = (
            isinstance(voucher.check_in_date, date)
            and isinstance(voucher.check_out_date, date)
            and voucher.check_out_date > voucher.check_in_date
        )
        if room_number and has_valid_dates:
            reservation = create_backtrack_reservation(
                customer_name=voucher.customer_name,
                voucher_number=voucher.voucher_number or '',
                room_number=room_number,
                check_in_date=voucher.check_in_date,
                check_out_date=voucher.check_out_date,
                notes='',
            )
            if reservation:
                def link_voucher():
                    try:
                        voucher.reservation = reservation
                        voucher.is_confirmed = True
                        voucher.save(update_fields=['reservation', 'is_confirmed'])
                    except Exception:
                        logger.exception("Failed to link backtrack voucher to reservation")
                transaction.on_commit(link_voucher)
                messages.success(request, f'Backtrack reservation confirmed for {reservation.customer_name} in Room {reservation.room_number}.')
                return redirect('backtrack:backtrack_list')
            messages.error(request, 'Could not create backtrack reservation. Please check your data.')
        elif not has_valid_dates and (check_in_str or check_out_str):
            messages.error(request, 'Please set valid check-in and check-out dates.')
        else:
            messages.error(request, 'Please select a room and ensure dates are set.')

    context = {
        'voucher': voucher,
    }

    return render(request, 'backtrack/review_backtrack.html', context)


@login_required
def backtrack_list(request):
    """List all backtrack reservations with search."""
    reservations = BacktrackReservation.objects.order_by('-check_in_date')
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

    context = {
        'page_obj': page_obj,
        'search_name': search_name,
        'search_voucher': search_voucher,
        'start_date': start_date,
        'end_date': end_date,
    }
    return render(request, 'backtrack/backtrack_list.html', context)


@login_required
def backtrack_report(request):
    """Generate reports for backtrack reservations."""
    mode = request.GET.get('mode', 'daily')

    # Default date: use latest backtrack reservation check_in_date, not today
    latest = BacktrackReservation.objects.order_by('-check_in_date').first()
    default_date = latest.check_in_date if latest else date.today()
    date_str = request.GET.get('date', default_date.strftime('%y/%m/%d'))
    try:
        anchor_date = parse_date_safe(date_str) or default_date
    except ValueError:
        anchor_date = default_date

    if mode == 'weekly':
        start_date = anchor_date - timedelta(days=anchor_date.weekday())
        end_date = start_date + timedelta(days=6)
    elif mode == 'monthly':
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
            start_date = parse_date_safe(start_str) if start_str else anchor_date
        except ValueError:
            start_date = anchor_date
        try:
            end_date = parse_date_safe(end_str) if end_str else start_date
        except ValueError:
            end_date = start_date
        if end_date < start_date:
            end_date = start_date
    else:
        mode = 'daily'
        start_date = end_date = anchor_date

    check_ins = BacktrackReservation.objects.filter(
        check_in_date__gte=start_date,
        check_in_date__lte=end_date,
        status='confirmed'
    ).order_by('room_number')

    check_outs = BacktrackReservation.objects.filter(
        check_out_date__gte=start_date,
        check_out_date__lte=end_date,
        status='confirmed'
    ).order_by('room_number')

    total = BacktrackReservation.objects.filter(
        check_in_date__lt=end_date + timedelta(days=1),
        check_out_date__gt=start_date,
        status='confirmed'
    ).values('room_number').distinct().count()

    if start_date == end_date:
        date_label = start_date.strftime('%y/%m/%d')
    else:
        date_label = f"{start_date.strftime('%y/%m/%d')} – {end_date.strftime('%y/%m/%d')}"

    export_format = request.GET.get('export')
    if export_format == 'pdf':
        return generate_backtrack_pdf_report(date_label, check_ins, check_outs, total, mode)
    elif export_format == 'excel':
        return generate_backtrack_excel_report(date_label, check_ins, check_outs, total, mode)

    context = {
        'mode': mode,
        'anchor_date': anchor_date,
        'start_date': start_date,
        'end_date': end_date,
        'date_label': date_label,
        'check_ins': check_ins,
        'check_outs': check_outs,
        'total': total,
    }
    return render(request, 'backtrack/reports.html', context)


@login_required
def delete_backtrack_reservation(request, pk):
    """Delete a backtrack reservation."""
    reservation = get_object_or_404(BacktrackReservation, pk=pk)
    if request.method == 'POST':
        reservation.delete()
        messages.success(request, f'Backtrack reservation for {reservation.customer_name} has been deleted.')
    return redirect('backtrack:backtrack_list')


@login_required
def delete_backtrack_from_dashboard(request, pk):
    """Delete a backtrack reservation from dashboard."""
    reservation = get_object_or_404(BacktrackReservation, pk=pk)
    if request.method == 'POST':
        reservation.delete()
        messages.success(request, f'Backtrack reservation for {reservation.customer_name} has been deleted.')
    return redirect('backtrack:dashboard')


def generate_backtrack_pdf_report(date_label, check_ins, check_outs, total, mode):
    """Generate PDF report for backtrack reservations using room_number string field."""
    import os
    from django.conf import settings
    from django.http import HttpResponse
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="backtrack_report_{date_label.replace("/", "-")}.pdf"'

    doc = SimpleDocTemplate(
        response,
        pagesize=letter,
        leftMargin=0.75*inch,
        rightMargin=0.75*inch,
        topMargin=0.15*inch,
        bottomMargin=0.75*inch,
    )
    elements = []
    styles = getSampleStyleSheet()

    contact_lines = [
        '<font color="#D4AF37" size="16">★ ★ ★ ★</font>',
        '<b><font size="18">Ulendo Lodge & Apartments</font></b>',
        '<font size="14" color="#444444">10 Sinclair Road, Lambton, Germiston, 1401</font>',
        '<font size="13" color="#555555">Tel: 067 623 7170 &nbsp;&nbsp; Tel: 010 824 4595</font>',
        '<font size="13" color="#555555">Email: info@ulendolodge.com</font>',
        '<font size="13" color="#666666">Reg Nr. 2016/078946/07</font>',
    ]
    contact_text = '<br/>'.join(contact_lines)
    contact_style = ParagraphStyle(
        'Contact',
        parent=styles['Normal'],
        fontSize=14,
        textColor=colors.HexColor('#333333'),
        alignment=1,
        leftIndent=0,
        rightIndent=0,
        spaceBefore=0,
        spaceAfter=2,
        leading=19,
    )
    logo_path = os.path.join(settings.BASE_DIR, 'assets', 'logo.png')
    logo_img = None
    if os.path.exists(logo_path):
        try:
            logo_img = Image(logo_path, width=3.0 * inch, height=3.0 * inch)
            logo_img.hAlign = 'CENTER'
        except Exception:
            pass
    contact_para = Paragraph(contact_text, contact_style)
    if logo_img:
        header_data = [[logo_img], [Spacer(1, 0.08*inch)], [contact_para]]
        header_table = Table(header_data, colWidths=[5.5*inch])
        header_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
        ]))
    else:
        header_data = [[contact_para]]
        header_table = Table(header_data, colWidths=[5.5*inch])
        header_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ]))
    elements.append(header_table)
    elements.append(Spacer(1, 0.25 * inch))

    line_table = Table([['']], colWidths=[6.5*inch])
    line_table.setStyle(TableStyle([
        ('LINEBELOW', (0, 0), (-1, 0), 0.5, colors.HexColor('#DDDDDD')),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(line_table)
    elements.append(Spacer(1, 0.2 * inch))

    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#C77A1A'),
        spaceAfter=30,
    )
    mode_label_map = {'daily': 'Daily', 'weekly': 'Weekly', 'monthly': 'Monthly', 'custom': 'Custom Range'}
    mode_label = mode_label_map.get(mode, 'Daily')
    title_text = f'Backtrack {mode_label} Report - {date_label}'
    elements.append(Paragraph(title_text, title_style))
    elements.append(Spacer(1, 0.2*inch))

    elements.append(Paragraph(f'<b>Report type:</b> {mode_label}', styles['Normal']))
    elements.append(Paragraph(f'<b>Period:</b> {date_label}', styles['Normal']))
    elements.append(Spacer(1, 0.2*inch))

    seen_ids = set()
    all_reservations = []
    for r in list(check_ins) + list(check_outs):
        if r.id not in seen_ids:
            seen_ids.add(r.id)
            all_reservations.append(r)
    all_reservations.sort(key=lambda r: (r.room_number, r.check_in_date))

    if all_reservations:
        elements.append(Paragraph('<b>Booking Information</b>', styles['Heading2']))
        booking_data = [['Room', 'Voucher', 'Customer', 'Check-in', 'Check-out']]
        for res in all_reservations:
            booking_data.append([
                f"Room {res.room_number}",
                res.voucher_number or '-',
                res.customer_name,
                res.check_in_date.strftime('%y/%m/%d'),
                res.check_out_date.strftime('%y/%m/%d')
            ])
        col_widths = [1.2*inch, 1.8*inch, 2.4*inch, 1.4*inch, 1.4*inch]
        table = Table(booking_data, colWidths=col_widths)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0F0F0F')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        elements.append(table)
        elements.append(Spacer(1, 0.3*inch))

    summary_data = [
        ['Total Records', str(total)],
    ]
    table = Table(summary_data, colWidths=[3*inch, 2*inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#C77A1A')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(table)

    doc.build(elements)
    return response


def generate_backtrack_excel_report(date_label, check_ins, check_outs, total, mode):
    """Generate Excel report for backtrack reservations using room_number string field."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill
    from django.http import HttpResponse

    wb = Workbook()
    ws = wb.active
    ws.title = 'Backtrack Report'

    header_fill = PatternFill(start_color='C77A1A', end_color='C77A1A', fill_type='solid')
    header_font = Font(bold=True, color='FFFFFF', size=12)

    ws['A1'] = f'Backtrack Report - {date_label}'
    ws['A1'].font = Font(bold=True, size=14, color='C77A1A')
    ws.merge_cells('A1:E1')

    row = 3

    ws[f'A{row}'] = 'Check-ins'
    ws[f'A{row}'].font = Font(bold=True, size=12)
    row += 1

    headers = ['Room', 'Voucher', 'Customer', 'Check-in', 'Check-out']
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=row, column=col)
        cell.value = header
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')

    row += 1
    for res in check_ins:
        ws.cell(row=row, column=1, value=f"Room {res.room_number}")
        ws.cell(row=row, column=2, value=res.voucher_number or '-')
        ws.cell(row=row, column=3, value=res.customer_name)
        ws.cell(row=row, column=4, value=res.check_in_date.strftime('%y/%m/%d'))
        ws.cell(row=row, column=5, value=res.check_out_date.strftime('%y/%m/%d'))
        row += 1

    row += 2

    ws[f'A{row}'] = 'Check-outs'
    ws[f'A{row}'].font = Font(bold=True, size=12)
    row += 1

    headers = ['Room', 'Voucher', 'Customer', 'Check-in', 'Check-out']
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=row, column=col)
        cell.value = header
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')

    row += 1
    for res in check_outs:
        ws.cell(row=row, column=1, value=f"Room {res.room_number}")
        ws.cell(row=row, column=2, value=res.voucher_number or '-')
        ws.cell(row=row, column=3, value=res.customer_name)
        ws.cell(row=row, column=4, value=res.check_in_date.strftime('%y/%m/%d'))
        ws.cell(row=row, column=5, value=res.check_out_date.strftime('%y/%m/%d'))
        row += 1

    row += 2

    ws[f'A{row}'] = 'Summary'
    ws[f'A{row}'].font = Font(bold=True, size=12)
    row += 1

    ws.cell(row=row, column=1, value='Total Records').font = Font(bold=True)
    ws.cell(row=row, column=2, value=total)

    for column in ws.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = min(max_length + 2, 50)
        ws.column_dimensions[column_letter].width = adjusted_width

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="backtrack_report_{date_label.replace("/", "-")}.xlsx"'
    wb.save(response)
    return response
