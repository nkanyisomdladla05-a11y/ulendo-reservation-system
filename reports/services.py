import os

from django.conf import settings
from django.http import HttpResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
from datetime import date


def generate_pdf_report(report_type, report_date, data):
    """Generate PDF report using reportlab."""
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{report_type}_report_{report_date}.pdf"'
    
    doc = SimpleDocTemplate(response, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()

    # Optional logo + brand header
    logo_path = os.path.join(settings.BASE_DIR, 'assets', 'logo.png')
    if os.path.exists(logo_path):
        try:
            logo = Image(logo_path, width=1.0 * inch, height=1.0 * inch)
            logo.hAlign = 'LEFT'
            elements.append(logo)
            elements.append(Spacer(1, 0.15 * inch))
        except Exception:
            # If logo fails to load, continue without breaking the report
            pass

    brand_style = ParagraphStyle(
        'Brand',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#555555'),
        spaceAfter=4,
    )
    elements.append(Paragraph('Ulendo Reservation System', brand_style))

    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#C77A1A'),
        spaceAfter=30,
    )
    # For daily-style reports we may have range modes (daily/weekly/monthly/custom)
    if report_type == 'daily':
        mode = data.get('mode', 'daily')
        mode_label_map = {
            'daily': 'Daily',
            'weekly': 'Weekly',
            'monthly': 'Monthly',
            'custom': 'Custom Range',
        }
        mode_label = mode_label_map.get(mode, 'Daily')
        title_text = f'{mode_label} Report - {report_date}'
    elif report_type == 'monthly':
        # Monthly exports still use the month as the title date
        if isinstance(report_date, date):
            title_text = f'Monthly Report - {report_date.strftime("%B %Y")}'
        else:
            title_text = f'Monthly Report - {report_date}'
    else:
        title_text = f'{report_type.title()} Report - {report_date}'

    elements.append(Paragraph(title_text, title_style))
    elements.append(Spacer(1, 0.2*inch))
    
    if report_type == 'daily':
        # Daily/weekly/monthly/custom (range) report content
        range_label = data.get('date_label', str(report_date))
        mode = data.get('mode', 'daily')
        mode_label_map = {
            'daily': 'Daily',
            'weekly': 'Weekly',
            'monthly': 'Monthly',
            'custom': 'Custom Range',
        }
        mode_label = mode_label_map.get(mode, 'Daily')

        elements.append(Paragraph(f'<b>Report type:</b> {mode_label}', styles['Normal']))
        elements.append(Paragraph(f'<b>Period:</b> {range_label}', styles['Normal']))
        elements.append(Spacer(1, 0.2*inch))
        
        # Check-ins table
        if data['check_ins']:
            elements.append(Paragraph('<b>Check-ins:</b>', styles['Heading2']))
            check_in_data = [['Room', 'Customer', 'Check-out']]
            for reservation in data['check_ins']:
                check_in_data.append([
                    f"Room {reservation.room.room_number}",
                    reservation.customer_name,
                    reservation.check_out_date.strftime('%Y-%m-%d')
                ])
            table = Table(check_in_data)
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
        
        # Check-outs table
        if data['check_outs']:
            elements.append(Paragraph('<b>Check-outs:</b>', styles['Heading2']))
            check_out_data = [['Room', 'Customer', 'Check-in']]
            for reservation in data['check_outs']:
                check_out_data.append([
                    f"Room {reservation.room.room_number}",
                    reservation.customer_name,
                    reservation.check_in_date.strftime('%Y-%m-%d')
                ])
            table = Table(check_out_data)
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
        
        # Summary
        summary_data = [
            ['Total Rooms', str(data['total_rooms'])],
            ['Booked Rooms', str(data['booked_rooms'])],
            ['Occupancy Rate', f"{data['occupancy_rate']:.1f}%"],
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
    
    elif report_type == 'monthly':
        # Monthly report content
        elements.append(Paragraph(f'<b>Month:</b> {report_date.strftime("%B %Y")}', styles['Normal']))
        elements.append(Spacer(1, 0.2*inch))
        
        # Summary
        summary_data = [
            ['Total Bookings', str(data['total_bookings'])],
            ['Average Occupancy', f"{data['avg_occupancy']:.1f}%"],
            ['Total Rooms', str(data['total_rooms'])],
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


def generate_excel_report(report_type, report_date, data):
    """Generate Excel report using openpyxl."""
    wb = Workbook()
    ws = wb.active
    ws.title = f'{report_type.title()} Report'
    
    # Header style
    header_fill = PatternFill(start_color='C77A1A', end_color='C77A1A', fill_type='solid')
    header_font = Font(bold=True, color='FFFFFF', size=12)
    
    # Title
    ws['A1'] = f'{report_type.title()} Report - {report_date}'
    ws['A1'].font = Font(bold=True, size=14, color='C77A1A')
    ws.merge_cells('A1:D1')
    
    row = 3
    
    if report_type == 'daily':
        # Check-ins
        ws[f'A{row}'] = 'Check-ins'
        ws[f'A{row}'].font = Font(bold=True, size=12)
        row += 1
        
        headers = ['Room', 'Customer', 'Check-out']
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=row, column=col)
            cell.value = header
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center')
        
        row += 1
        for reservation in data['check_ins']:
            ws.cell(row=row, column=1, value=f"Room {reservation.room.room_number}")
            ws.cell(row=row, column=2, value=reservation.customer_name)
            ws.cell(row=row, column=3, value=reservation.check_out_date.strftime('%Y-%m-%d'))
            row += 1
        
        row += 2
        
        # Check-outs
        ws[f'A{row}'] = 'Check-outs'
        ws[f'A{row}'].font = Font(bold=True, size=12)
        row += 1
        
        headers = ['Room', 'Customer', 'Check-in']
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=row, column=col)
            cell.value = header
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center')
        
        row += 1
        for reservation in data['check_outs']:
            ws.cell(row=row, column=1, value=f"Room {reservation.room.room_number}")
            ws.cell(row=row, column=2, value=reservation.customer_name)
            ws.cell(row=row, column=3, value=reservation.check_in_date.strftime('%Y-%m-%d'))
            row += 1
        
        row += 2
        
        # Summary
        ws[f'A{row}'] = 'Summary'
        ws[f'A{row}'].font = Font(bold=True, size=12)
        row += 1
        
        summary_data = [
            ['Total Rooms', data['total_rooms']],
            ['Booked Rooms', data['booked_rooms']],
            ['Occupancy Rate', f"{data['occupancy_rate']:.1f}%"],
        ]
        
        for item in summary_data:
            ws.cell(row=row, column=1, value=item[0]).font = Font(bold=True)
            ws.cell(row=row, column=2, value=item[1])
            row += 1
    
    elif report_type == 'monthly':
        # Summary
        ws['A3'] = 'Summary'
        ws['A3'].font = Font(bold=True, size=12)
        
        summary_data = [
            ['Total Bookings', data['total_bookings']],
            ['Average Occupancy', f"{data['avg_occupancy']:.1f}%"],
            ['Total Rooms', data['total_rooms']],
        ]
        
        row = 4
        for item in summary_data:
            ws.cell(row=row, column=1, value=item[0]).font = Font(bold=True)
            ws.cell(row=row, column=2, value=item[1])
            row += 1
    
    # Auto-adjust column widths
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
    response['Content-Disposition'] = f'attachment; filename="{report_type}_report_{report_date}.xlsx"'
    wb.save(response)
    return response
