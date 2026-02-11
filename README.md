<<<<<<< HEAD
# Ulendo Reservation System

A production-ready Django web application for managing lodge reservations with 30 rooms, OCR voucher processing, date overlap prevention, and comprehensive reporting.

## Features

- **Room Management**: 30 pre-populated rooms with optional room types
- **Reservation System**: Create reservations with automatic double-booking prevention
- **Two Booking Flows**:
  - Manual booking with form entry
  - Voucher upload with OCR extraction (customer name, voucher number, dates)
- **OCR Processing**: Automatic extraction and editable review of voucher data
- **Room Availability**: View room status by date range with filtering
- **Search & Filter**: Search reservations by customer name, voucher number, or date range
- **Reporting**:
  - Daily check-ins and check-outs
  - Occupancy rate calculations
  - Monthly summary reports
  - PDF and Excel export capabilities
- **Modern UI**: Clean, professional interface with Ulendo branding

## Installation

1. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Install Tesseract OCR** (required for voucher OCR):
   - Windows: Download from https://github.com/UB-Mannheim/tesseract/wiki
   - macOS: `brew install tesseract`
   - Linux: `sudo apt-get install tesseract-ocr`

3. **Run migrations:**
   ```bash
   python manage.py migrate
   ```

4. **Create superuser (optional, for admin access):**
   ```bash
   python manage.py createsuperuser
   ```

5. **Run the development server:**
   ```bash
   python manage.py runserver
   ```

6. **Access the application:**
   - Open http://127.0.0.1:8000 in your browser
   - Login with: `info@ulendolodge.com` / `Ulendo@#2025!`

## Project Structure

```
ullendo_reservation/
├── rooms/              # Room management app
├── reservations/       # Core reservation logic
├── vouchers/          # OCR voucher processing
├── reports/           # Reporting and exports
├── accounts/          # Authentication
├── core/              # Shared templates and static files
└── ullendo_reservation/  # Project settings
```

## Database

The system uses SQLite by default (configured in `settings.py`). The database is designed to be PostgreSQL-compatible for easy migration.

## Usage

### Creating a Reservation

1. **Manual Booking:**
   - Navigate to "New Reservation"
   - Select "Manual Booking" tab
   - Enter customer details and dates
   - Submit to see available rooms
   - Select a room and confirm

2. **Voucher Upload:**
   - Navigate to "New Reservation"
   - Select "Upload Voucher" tab
   - Upload voucher image
   - Review and edit extracted data
   - Select available room
   - Confirm reservation

### Viewing Reports

- **Daily Report**: View check-ins, check-outs, and occupancy for a specific date
- **Monthly Report**: Monthly summary with booking statistics
- **Occupancy Report**: Room occupancy details for a specific date
- All reports can be exported to PDF or Excel

## Color Scheme (Ulendo Brand)

- Primary: #C77A1A (gold/bronze)
- Secondary: #0F0F0F (charcoal)
- Background: #F7F7F7
- Success: #1E9E5A
- Warning: #F4A261
- Error: #D64545
- Info: #2F80ED

## Technical Details

- **Framework**: Django 6.0+
- **Database**: SQLite (PostgreSQL-ready)
- **OCR**: pytesseract (Tesseract OCR engine)
- **PDF Export**: reportlab
- **Excel Export**: openpyxl
- **Date Parsing**: python-dateutil

## Production Deployment

For production deployment:

1. Set `DEBUG = False` in `settings.py`
2. Configure `ALLOWED_HOSTS`
3. Set up a production database (PostgreSQL recommended)
4. Configure static file serving
5. Set up proper media file storage
6. Use environment variables for sensitive settings

## License

Proprietary - Ulendo Lodge Reservation System
=======
# ulendo-reservation-system
>>>>>>> cb3fce1f4e6291fb36a3e6752e3afcebe52876fe
