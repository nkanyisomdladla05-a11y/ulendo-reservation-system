import re
import os
import pytesseract
from PIL import Image
from datetime import datetime, date
from dateutil import parser as date_parser


def extract_text_from_image(image_path):
    """
    Extract text from an image or PDF.

    - For PDFs: use PyMuPDF to read embedded text (no Tesseract required).
    - For images: use Tesseract OCR via pytesseract.
    
    Args:
        image_path: Path to the image or PDF file
    
    Returns:
        str: Extracted text
    """
    try:
        # Check if file is a PDF
        file_ext = os.path.splitext(image_path)[1].lower()
        
        if file_ext == '.pdf':
            # Prefer direct text extraction from PDF (works for non-scanned PDFs)
            try:
                import fitz  # PyMuPDF
                doc = fitz.open(image_path)
                if doc.page_count == 0:
                    doc.close()
                    raise Exception("PDF has no pages")
                
                text_chunks = []
                for page in doc:
                    # Extract text from each page
                    text_chunks.append(page.get_text())
                doc.close()
                text = "\n".join(text_chunks).strip()
                
                if not text:
                    # No embedded text found – likely a scanned PDF
                    # In this environment we avoid requiring Tesseract,
                    # so just return empty text and let the caller handle it.
                    raise Exception(
                        "No text found in PDF; it may be a scanned image that "
                        "requires OCR."
                    )
                return text
            except ImportError:
                raise Exception(
                    "PyMuPDF is required for PDF processing. Install it: pip install PyMuPDF"
                )
            except Exception as e:
                raise Exception(f"Error processing PDF: {str(e)}")
        else:
            # Handle regular image files with Tesseract OCR
            try:
                image = Image.open(image_path)
                text = pytesseract.image_to_string(image)
                return text
            except Exception as e:
                # Common case: Tesseract not installed / not in PATH.
                raise Exception(
                    "Image-based OCR failed. Tesseract may not be installed or "
                    f"not available: {str(e)}"
                )
    except Exception as e:
        raise Exception(f"Error extracting text from file: {str(e)}")


def parse_customer_name(text):
    """
    Extract customer name from OCR text.
    
    Priority:
    1. Look for a line labeled "Passenger name/s" or "Passenger name"
       and use that value (first passenger only if multiple).
    2. Fall back to generic patterns (name, customer, guest).
    
    Args:
        text: OCR extracted text
    
    Returns:
        str: Customer name or empty string
    """
    if not text:
        return ""

    # 1) Prefer explicit "Passenger name/s" style labels anywhere in the text.
    #    Handles cases where the value is on the same line OR on the next line.
    m = re.search(
        r"Passenger\s+name/?s?\s*[:\-]?\s*(.*)",
        text,
        re.IGNORECASE,
    )
    if m:
        line_after_label = m.group(1).strip()
        # If same line has only meta like "Number in party: 1", treat as empty
        if line_after_label and re.search(r"number\s+in\s+party", line_after_label, re.IGNORECASE):
            line_after_label = ""

        if not line_after_label:
            # Nothing usable after the label on the same line – use the next
            # non-empty line that follows the label
            remainder = text[m.end():]
            next_lines = remainder.splitlines()
            for nl in next_lines:
                candidate_line = nl.strip()
                if candidate_line:
                    line_after_label = candidate_line
                    break

        if line_after_label:
            candidate = line_after_label
            # If multiple passengers listed, take only the first
            for sep in [",", ";", "/", "&"]:
                if sep in candidate:
                    candidate = candidate.split(sep)[0].strip()
                    break
            if (
                len(candidate) > 2
                and candidate.lower() not in ["date", "check", "voucher", "number"]
            ):
                return candidate

    # 2) If we can't confidently match a Passenger name/s block,
    #    don't guess from other text. Let the user fill it manually.
    return ""


def parse_voucher_number(text):
    """
    Extract voucher number from OCR text.
    Looks for patterns like "Voucher:", "Voucher No:", "Ref:", etc.
    
    Args:
        text: OCR extracted text
    
    Returns:
        str: Voucher number or empty string
    """
    patterns = [
        r'(?:voucher|ref|reference|booking)[\s#:]+([A-Z0-9\-]+)',
        r'(?:voucher|ref|reference|booking)[\s#:]+([0-9]{4,})',
        r'([A-Z]{2,}[0-9]{3,})',  # Alphanumeric codes
        r'([0-9]{6,})',  # Long numeric codes
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            voucher_num = match.group(1).strip()
            if len(voucher_num) >= 4:
                return voucher_num
    
    return ""


def _parse_ymd_directly(date_str):
    """Parse YYYY/MM/DD or YYYY-MM-DD directly as year-month-day."""
    match = re.match(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', date_str)
    if match:
        try:
            year = int(match.group(1))
            month = int(match.group(2))
            day = int(match.group(3))
            return date(year, month, day)
        except (ValueError, OverflowError):
            return None
    return None


def _parse_dmy_directly(date_str):
    """Parse DD/MM/YYYY or DD-MM-YYYY directly as day-month-year."""
    match = re.match(r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})', date_str)
    if match:
        try:
            day = int(match.group(1))
            month = int(match.group(2))
            year = int(match.group(3))
            return date(year, month, day)
        except (ValueError, OverflowError):
            return None
    return None


def _normalize_raw_date(date_obj):
    """Convert a date object to YYYY/MM/DD string."""
    if date_obj is None:
        return None
    return date_obj.strftime('%Y/%m/%d')


def _find_date_near_label(text, label_pattern, start_after_pos=0):
    """
    Find a date near a label occurrence in text.
    Searches from start_after_pos onward.
    Returns (date_obj, raw_str, match_end_pos) or (None, None, None).
    """
    match = re.search(label_pattern, text[start_after_pos:], re.IGNORECASE)
    if not match:
        return None, None, None

    abs_match_start = start_after_pos + match.start()
    abs_match_end = start_after_pos + match.end()

    # Get the line containing the label and the next 2 lines
    line_start = text.rfind('\n', 0, abs_match_start)
    if line_start == -1:
        line_start = 0
    # Find end of 2nd line after the label
    search_from = abs_match_end
    for _ in range(2):
        nl = text.find('\n', search_from)
        if nl == -1:
            search_from = len(text)
            break
        search_from = nl + 1

    nearby_text = text[line_start:search_from]

    # Look for YYYY/MM/DD first (most reliable)
    ymd_match = re.search(r'(\d{4}[/-]\d{1,2}[/-]\d{1,2})', nearby_text)
    if ymd_match:
        parsed = _parse_ymd_directly(ymd_match.group(1))
        if parsed:
            return parsed, ymd_match.group(1), abs_match_end

    # Look for DD/MM/YYYY
    dmy_match = re.search(r'(\d{1,2}[/-]\d{1,2}[/-]\d{4})', nearby_text)
    if dmy_match:
        parsed = _parse_dmy_directly(dmy_match.group(1))
        if parsed:
            return parsed, dmy_match.group(1), abs_match_end

    # Look for text dates
    text_date_match = re.search(r'(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{2,4})', nearby_text, re.IGNORECASE)
    if text_date_match:
        try:
            parsed = date_parser.parse(text_date_match.group(1), dayfirst=True).date()
            return parsed, text_date_match.group(1), abs_match_end
        except:
            pass

    return None, None, abs_match_end


def parse_dates(text):
    """
    Extract check-in and check-out dates from OCR text.

    Strategy:
    1. Phase 1: Search for SPECIFIC labels (check-in, check-out, checkin, checkout)
    2. Phase 2: Only if Phase 1 fails, search for GENERIC labels (arrival, departure, from, to, etc.)
    3. For each label, search line-by-line to find the occurrence that has a date nearby
    4. All raw dates normalized to YYYY/MM/DD format

    This prevents false matches like "TO:" (destination) being confused with "to" (departure date).
    """
    check_in_date = None
    check_out_date = None
    check_in_raw = None
    check_out_raw = None

    # Phase 1: Specific labels only (unambiguous)
    specific_checkin = r'(?:check[-\s]?in|checkin)'
    specific_checkout = r'(?:check[-\s]?out|checkout)'

    # Phase 2: Generic labels (fallback only)
    generic_checkin = r'(?:arrival|from|start\s*date|arrive)'
    generic_checkout = r'(?:departure|to|end\s*date|depart)'

    lines = text.split('\n')

    def find_date_for_label(label_pattern, lines, skip_labels=None):
        """Find a date for a label by scanning all lines. Returns (date, raw) or (None, None)."""
        for i, line in enumerate(lines):
            match = re.search(label_pattern, line, re.IGNORECASE)
            if not match:
                continue
            # Check if this line matches a label we should skip
            if skip_labels:
                skip_match = re.search(skip_labels, line, re.IGNORECASE)
                if skip_match:
                    continue

            # Look for date on this line (after the label)
            after_label = line[match.end():].strip()
            if after_label:
                ymd = re.search(r'(\d{4}[/-]\d{1,2}[/-]\d{1,2})', after_label)
                if ymd:
                    parsed = _parse_ymd_directly(ymd.group(1))
                    if parsed:
                        return parsed, ymd.group(1)
                dmy = re.search(r'(\d{1,2}[/-]\d{1,2}[/-]\d{4})', after_label)
                if dmy:
                    parsed = _parse_dmy_directly(dmy.group(1))
                    if parsed:
                        return parsed, dmy.group(1)

            # Look for date on the next line
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                ymd = re.search(r'(\d{4}[/-]\d{1,2}[/-]\d{1,2})', next_line)
                if ymd:
                    parsed = _parse_ymd_directly(ymd.group(1))
                    if parsed:
                        return parsed, ymd.group(1)
                dmy = re.search(r'(\d{1,2}[/-]\d{1,2}[/-]\d{4})', next_line)
                if dmy:
                    parsed = _parse_dmy_directly(dmy.group(1))
                    if parsed:
                        return parsed, dmy.group(1)

        return None, None

    # Phase 1: Specific labels
    check_in_date, check_in_raw = find_date_for_label(specific_checkin, lines)
    check_out_date, check_out_raw = find_date_for_label(specific_checkout, lines)

    # Phase 2: Generic labels (only if Phase 1 didn't find both)
    if not check_in_date:
        check_in_date, check_in_raw = find_date_for_label(generic_checkin, lines)
    if not check_out_date:
        # For generic checkout, skip lines that are actually destination addresses
        # (lines with "TO:" followed by hotel/address info, not dates)
        check_out_date, check_out_raw = find_date_for_label(generic_checkout, lines)

    # Fallback: find all YYYY/MM/DD dates in text
    if not check_in_date or not check_out_date:
        all_dates = []
        for m in re.finditer(r'(\d{4}[/-]\d{1,2}[/-]\d{1,2})', text):
            parsed = _parse_ymd_directly(m.group(1))
            if parsed:
                all_dates.append((parsed, m.group(1)))

        if not check_in_date and len(all_dates) >= 1:
            check_in_date, check_in_raw = all_dates[0]
        if not check_out_date and len(all_dates) >= 2:
            check_out_date, check_out_raw = all_dates[1]

    # Normalize raw dates to YYYY/MM/DD
    if check_in_date and check_in_raw:
        check_in_raw = _normalize_raw_date(check_in_date)
    if check_out_date and check_out_raw:
        check_out_raw = _normalize_raw_date(check_out_date)

    return {
        'check_in_date': check_in_date,
        'check_out_date': check_out_date,
        'check_in_raw': check_in_raw,
        'check_out_raw': check_out_raw,
    }


def extract_voucher_data(image_path):
    """
    Extract all voucher data from an image.

    Args:
        image_path: Path to the voucher image

    Returns:
        dict: Dictionary with extracted data:
            - customer_name: str
            - voucher_number: str
            - check_in_date: date or None
            - check_out_date: date or None
            - check_in_raw: str or None
            - check_out_raw: str or None
            - raw_text: str
    """
    raw_text = extract_text_from_image(image_path)

    customer_name = parse_customer_name(raw_text)
    voucher_number = parse_voucher_number(raw_text)
    date_info = parse_dates(raw_text)

    return {
        'customer_name': customer_name,
        'voucher_number': voucher_number,
        'check_in_date': date_info['check_in_date'],
        'check_out_date': date_info['check_out_date'],
        'check_in_raw': date_info['check_in_raw'],
        'check_out_raw': date_info['check_out_raw'],
        'raw_text': raw_text,
    }
