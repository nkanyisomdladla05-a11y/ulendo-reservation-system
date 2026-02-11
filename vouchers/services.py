import re
import os
import pytesseract
from PIL import Image
from datetime import datetime
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


def parse_dates(text):
    """
    Extract check-in and check-out dates from OCR text.
    Handles multiple date formats.
    
    Args:
        text: OCR extracted text
    
    Returns:
        tuple: (check_in_date, check_out_date) as date objects or (None, None)
    """
    # Common date patterns
    date_patterns = [
        r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}',  # DD/MM/YYYY or MM/DD/YYYY
        r'\d{4}[/-]\d{1,2}[/-]\d{1,2}',  # YYYY-MM-DD
        r'\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{2,4}',  # DD Mon YYYY
    ]
    
    dates = []
    for pattern in date_patterns:
        matches = re.findall(pattern, text)
        dates.extend(matches)
    
    # Try to parse dates
    parsed_dates = []
    for date_str in dates:
        try:
            # Try multiple parsing strategies
            parsed = date_parser.parse(date_str, dayfirst=True, fuzzy=True)
            parsed_dates.append(parsed.date())
        except:
            try:
                parsed = date_parser.parse(date_str, dayfirst=False, fuzzy=True)
                parsed_dates.append(parsed.date())
            except:
                continue
    
    # Look for check-in/check-out keywords
    check_in_date = None
    check_out_date = None
    
    # Search for "check in" and "check out" patterns
    check_in_patterns = [
        r'(?:check[-\s]?in|arrival|from)[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
        r'(?:check[-\s]?in|arrival|from)[:\s]+(\d{4}[/-]\d{1,2}[/-]\d{1,2})',
    ]
    
    check_out_patterns = [
        r'(?:check[-\s]?out|departure|to)[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
        r'(?:check[-\s]?out|departure|to)[:\s]+(\d{4}[/-]\d{1,2}[/-]\d{1,2})',
    ]
    
    for pattern in check_in_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                check_in_date = date_parser.parse(match.group(1), dayfirst=True).date()
                break
            except:
                continue
    
    for pattern in check_out_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                check_out_date = date_parser.parse(match.group(1), dayfirst=True).date()
                break
            except:
                continue
    
    # If we found dates but no specific labels, assume first is check-in, second is check-out
    if not check_in_date and len(parsed_dates) >= 1:
        check_in_date = parsed_dates[0]
    
    if not check_out_date and len(parsed_dates) >= 2:
        check_out_date = parsed_dates[1]
    elif not check_out_date and len(parsed_dates) == 1:
        # If only one date found, might be check-in, check-out could be next day or need manual entry
        pass
    
    return check_in_date, check_out_date


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
            - raw_text: str (full OCR text)
    """
    # Extract text
    raw_text = extract_text_from_image(image_path)
    
    # Parse fields
    customer_name = parse_customer_name(raw_text)
    voucher_number = parse_voucher_number(raw_text)
    check_in_date, check_out_date = parse_dates(raw_text)
    
    return {
        'customer_name': customer_name,
        'voucher_number': voucher_number,
        'check_in_date': check_in_date,
        'check_out_date': check_out_date,
        'raw_text': raw_text,
    }
