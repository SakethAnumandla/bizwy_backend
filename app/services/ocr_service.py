import re
import subprocess
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# Currency symbol optional; amounts may be 27.5 or 605
AMOUNT = r"(\d+(?:\.\d{1,2})?)"
CURRENCY_PREFIX = r"(?:₹|€|\$|Rs\.?)?\s*"


class OCRProcessor:
    def __init__(self):
        pass

    def _normalize_ocr_text(self, text: str) -> str:
        """Fix common Tesseract quirks before parsing."""
        text = (
            text.replace("\u2018", "'")
            .replace("\u2019", "'")
            .replace("\u201c", '"')
            .replace("\u201d", '"')
        )
        return text

    def _normalize_tax_amount(
        self, amount: float, line: str, subtotal: Optional[float]
    ) -> float:
        """Correct missing decimal (e.g. 275 -> 27.5 when rate is 5% of 550)."""
        rate_m = re.search(r"(\d+(?:\.\d+)?)\s*%", line)
        rate = float(rate_m.group(1)) if rate_m else None

        if subtotal and rate:
            expected = round(subtotal * rate / 100, 2)
            if expected > 0:
                for divisor in (10, 100):
                    scaled = round(amount / divisor, 2)
                    if abs(scaled - expected) <= max(1.5, expected * 0.2):
                        return scaled
                if abs(amount - expected) <= max(1.5, expected * 0.2):
                    return amount
                if amount > expected * 2:
                    return expected

        if subtotal and amount > subtotal * 0.12:
            for divisor in (10, 100):
                scaled = round(amount / divisor, 2)
                if scaled < subtotal * 0.12:
                    return scaled
        return amount

    def process_image_sync(self, image_path: str) -> Dict[str, Any]:
        import pytesseract
        from PIL import Image, ImageOps, ImageFilter

        text = ""
        try:
            import cv2

            image = cv2.imread(image_path)
            if image is not None:
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                denoised = cv2.fastNlMeansDenoising(gray, None, 30, 7, 21)
                thresh = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
                text = pytesseract.image_to_string(thresh)
        except Exception:
            text = ""

        if not text.strip():
            img = Image.open(image_path)
            img = ImageOps.grayscale(img)
            img = ImageOps.autocontrast(img)
            img = img.filter(ImageFilter.SHARPEN)
            text = pytesseract.image_to_string(img)

        extracted = self._parse_bill_text(text)
        extracted["raw_text"] = text
        return extracted

    def _extract_pdf_text(self, pdf_path: str) -> str:
        """Prefer embedded PDF text (accurate for email receipts like Uber)."""
        try:
            result = subprocess.run(
                ["pdftotext", "-layout", pdf_path, "-"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass
        return ""

    def process_pdf_sync(self, pdf_path: str) -> Dict[str, Any]:
        import os
        import pdf2image

        text = self._extract_pdf_text(pdf_path)
        if len(text.strip()) > 80:
            extracted = self._parse_bill_text(text)
            extracted["raw_text"] = text
            return extracted

        images = pdf2image.convert_from_path(
            pdf_path, first_page=1, last_page=1, dpi=300
        )
        if not images:
            return {}
        temp_image_path = pdf_path.replace(".pdf", "_page1.jpg")
        images[0].save(temp_image_path, "JPEG")
        try:
            return self.process_image_sync(temp_image_path)
        finally:
            if os.path.exists(temp_image_path):
                os.remove(temp_image_path)

    async def process_image(self, image_path: str) -> Dict[str, Any]:
        return self.process_image_sync(image_path)

    async def process_pdf(self, pdf_path: str) -> Dict[str, Any]:
        return self.process_pdf_sync(pdf_path)

    def _amount_from_line(self, line: str) -> Optional[float]:
        """Last monetary amount on a line (prefers decimals like 27.5)."""
        matches = re.findall(r"\d+\.\d{1,2}|\d+", line.replace(",", ""))
        if not matches:
            return None
        # Prefer last decimal amount (tax lines); else last number
        for m in reversed(matches):
            if "." in m:
                return float(m)
        return float(matches[-1])

    def _parse_payment_method(self, text: str) -> Optional[str]:
        """Detect Cash, UPI, Card, etc."""
        known = {
            "cash": "cash",
            "upi": "upi",
            "card": "credit_card",
            "credit": "credit_card",
            "debit": "debit_card",
            "net banking": "net_banking",
            "wallet": "wallet",
            "paytm": "wallet",
            "gpay": "upi",
            "phonepe": "upi",
        }
        patterns = [
            r"Mode\s*of\s*Payment[:\s]*([A-Za-z][A-Za-z\s]*)",
            r"Mode\s*of\s*Payment[:\s]*([A-Za-z]+)",
            r"Mode[:\s]*([A-Za-z]+)",
            r"Payment\s+Mode[:\s]*([A-Za-z]+)",
            r"Paid\s*(?:via|by)?[:\s]*([A-Za-z]+)",
        ]
        for pattern in patterns:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                val = m.group(1).strip().lower()
                if len(val) < 3:
                    continue
                for key, normalized in known.items():
                    if key in val or val == key:
                        return normalized
                return val

        pay_block = re.search(
            r"Payments\s*\n\s*(Cash|UPI|Card|Wallet|Paytm|GPay|PhonePe)",
            text,
            re.IGNORECASE,
        )
        if pay_block:
            val = pay_block.group(1).lower()
            return known.get(val, val)

        for line in text.splitlines():
            lower = line.lower()
            if "mode" in lower or "payment" in lower:
                for key, normalized in known.items():
                    if re.search(rf"\b{key}\b", lower):
                        return normalized
            if re.search(r"\bcash\b", lower) and (
                "mode" in lower or "payment" in lower or "total" in lower
            ):
                return "cash"
        return None

    def _parse_gst_tax(
        self,
        text: str,
        subtotal: Optional[float] = None,
        grand_total: Optional[float] = None,
    ) -> Tuple[Optional[float], Dict[str, float]]:
        """
        Parse CGST / SGST per line (not item rows). Handles OCR misreads like
        'cast' for CGST and 275 instead of 27.5.
        """
        breakdown: Dict[str, float] = {}
        gst_line = re.compile(
            r"(?i)\b(cgst|sgst|igst|cast)\b(?:\s*\([^)]*\))?",
        )

        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or "GST NO" in stripped.upper():
                continue
            m = gst_line.search(stripped)
            if not m:
                continue
            key = m.group(1).lower()
            if key == "cast":
                key = "cgst"
            amt = self._amount_from_line(stripped)
            if amt is None or amt >= 5000:
                continue
            amt = self._normalize_tax_amount(amt, stripped, subtotal)
            breakdown[key] = amt

        if breakdown:
            total = round(sum(breakdown.values()), 2)
            return total, breakdown

        if subtotal and grand_total:
            implied = round(grand_total - subtotal, 2)
            if 0 < implied < 500:
                half = round(implied / 2, 2)
                return implied, {"cgst": half, "sgst": implied - half}

        return None, breakdown

    def _parse_line_items(self, text: str) -> List[dict]:
        items: List[dict] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.upper().startswith(
                ("ITEM", "CGST", "SGST", "SUB", "CAST", "MODE")
            ):
                continue
            m = re.match(
                r"^([A-Za-z][A-Za-z\s']+?)\s+"
                r"(?:€|₹|\$)?\s*(\d+(?:\.\d+)?)\s+"
                r"(\d+)\s+"
                r"(?:€|₹|\$)?\s*(\d+(?:\.\d+)?)\s*$",
                stripped,
                re.IGNORECASE,
            )
            if m:
                name = m.group(1).strip()
                if any(x in name.lower() for x in ("total", "gst", "mode", "payment")):
                    continue
                items.append(
                    {
                        "name": name,
                        "unit_price": float(m.group(2)),
                        "quantity": int(m.group(3)),
                        "price": float(m.group(4)),
                    }
                )
        return items

    def _parse_ride_receipt(self, text: str, extracted: Dict[str, Any]) -> None:
        """Uber / Rapido / Ola ride receipts (email PDF or OCR)."""
        lower = text.lower()
        if not any(x in lower for x in ("uber", "rapido", "ola")):
            return

        if "uber" in lower:
            extracted["vendor_name"] = "Uber"
        elif "rapido" in lower:
            extracted["vendor_name"] = "Rapido"
        else:
            extracted["vendor_name"] = "Ola"

        gst_total = re.search(
            r"total of\s*[₹$€]?\s*([\d,]+\.?\d*)",
            text,
            re.IGNORECASE,
        )
        gst_tax = re.search(
            r"GST of\s*[₹$€]?\s*([\d,]+\.?\d*)",
            text,
            re.IGNORECASE,
        )
        trip_charge = re.search(
            r"Trip\s*charge\s*\n+\s*[₹$€]?\s*([\d,]+\.?\d*)",
            text,
            re.IGNORECASE,
        )
        total_block = re.search(
            r"(?<!Sub[-\s])Total\s*\n+\s*[₹$€]?\s*([\d,]+\.?\d*)",
            text,
            re.IGNORECASE,
        )

        for m in (gst_total, trip_charge, total_block):
            if m:
                amt = float(m.group(1).replace(",", ""))
                if amt < 50000:
                    extracted["total_amount"] = amt
                    break

        if gst_tax:
            tax = float(gst_tax.group(1).replace(",", ""))
            if tax < 5000:
                extracted["tax_amount"] = tax

        for pattern, formats in (
            (r"(\d{1,2}/\d{1,2}/\d{4})", ["%d/%m/%Y", "%d-%m-%Y"]),
            (
                r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s+(\w+\s+\d{1,2},?\s+\d{4})",
                ["%b %d, %Y", "%B %d, %Y"],
            ),
            (r"(\d{1,2}\s+[A-Za-z]+\s+\d{4})", ["%d %b %Y", "%d %B %Y"]),
        ):
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                raw = m.group(1).strip()
                for fmt in formats:
                    try:
                        extracted["bill_date"] = datetime.strptime(raw, fmt)
                        break
                    except ValueError:
                        continue
                if extracted.get("bill_date"):
                    break

        dist = re.search(
            r"(\d+(?:\.\d+)?)\s*kilomet(?:er|re)?s?",
            text,
            re.IGNORECASE,
        )
        if dist:
            extracted["ride_distance"] = float(dist.group(1))

        dur = re.search(r"(\d+)\s*minutes?", text, re.IGNORECASE)
        if dur:
            extracted["ride_duration"] = int(dur.group(1))

        ride_type = re.search(
            r"Trip details\s*\n+([^\n]+)\s*\n+\s*License Plate",
            text,
            re.IGNORECASE,
        )
        if ride_type:
            extracted["ride_type"] = ride_type.group(1).strip()

        trip_anchor = re.search(
            r"kilomet(?:er|re)?s?,\s*\d+\s*minutes?",
            text,
            re.IGNORECASE,
        )
        if trip_anchor:
            trip_text = text[trip_anchor.end() :]
            trip_end = re.search(
                r"Rate or tip|Want to review|My trips|Need help",
                trip_text,
                re.IGNORECASE,
            )
            if trip_end:
                trip_text = trip_text[: trip_end.start()]
            time_stops = list(re.finditer(r"\b(\d{2}:\d{2})\b", trip_text))
            if len(time_stops) >= 2:
                pickup_text = trip_text[time_stops[0].end() : time_stops[1].start()]
                drop_text = trip_text[time_stops[1].end() :]

                def _join_addr(block: str) -> str:
                    lines = [
                        ln.strip()
                        for ln in block.splitlines()
                        if ln.strip()
                        and not re.match(r"^[A-Z]{2}\d{2}[A-Z]{1,2}\d{4}$", ln.replace(" ", ""))
                        and not re.match(r"^\d+\.\d+$", ln)
                        and "License Plate" not in ln
                    ]
                    return ", ".join(lines)[:250]

                pickup_addr = _join_addr(pickup_text)
                drop_addr = _join_addr(drop_text)
                if pickup_addr:
                    extracted["pickup_location"] = pickup_addr
                if drop_addr:
                    extracted["dropoff_location"] = drop_addr

        if not extracted.get("payment_method"):
            if re.search(r"\bCash\b", text, re.IGNORECASE):
                extracted["payment_method"] = "cash"
            elif re.search(r"\bUPI\b", text, re.IGNORECASE):
                extracted["payment_method"] = "upi"

    def _parse_bill_text(self, text: str) -> Dict[str, Any]:
        text = self._normalize_ocr_text(text)
        extracted: Dict[str, Any] = {
            "bill_number": None,
            "bill_date": None,
            "vendor_name": None,
            "vendor_gst": None,
            "total_amount": None,
            "tax_amount": None,
            "tax_breakdown": {},
            "subtotal": None,
            "payment_method": None,
            "restaurant_name": None,
            "items_list": [],
            "customer_name": None,
            "table_number": None,
            "ride_distance": None,
            "ride_duration": None,
            "pickup_location": None,
            "dropoff_location": None,
            "ride_type": None,
            "confidence_score": 0.0,
        }

        self._parse_ride_receipt(text, extracted)

        # Invoice number (tolerate OCR: "nvoice Na: 1208")
        for pattern in (
            r"(?:I|1|i)?nvoice\s*(?:No|Na)[.:]?\s*#?\s*(\d+)",
            r"Invoice\s*No[.:]?\s*#?\s*(\d+)",
            r"Bill\s*No[.:]?\s*(\w+)",
        ):
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                extracted["bill_number"] = m.group(1).strip()
                break

        # Customer / table
        cust = re.search(r"Name[:\s]*([A-Za-z][A-Za-z\s]+)", text, re.IGNORECASE)
        if cust:
            extracted["customer_name"] = cust.group(1).strip()
        table = re.search(r"Table[:\s]*#?\s*(\d+)", text, re.IGNORECASE)
        if table:
            extracted["table_number"] = table.group(1)

        # Date
        date_patterns = [
            (r"Date[.:]?\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4})", ["%d %B %Y", "%d %b %Y"]),
            (r"Date[.:]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{4})", ["%d/%m/%Y", "%d-%m-%Y"]),
        ]
        for pattern, formats in date_patterns:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                for fmt in formats:
                    try:
                        extracted["bill_date"] = datetime.strptime(m.group(1).strip(), fmt)
                        break
                    except ValueError:
                        continue
                if extracted["bill_date"]:
                    break

        # Sub-total (explicit line only)
        for line in text.splitlines():
            if re.match(r"Sub[-\s]*Total", line.strip(), re.IGNORECASE):
                extracted["subtotal"] = self._amount_from_line(line)
                break

        # Grand total — last line with Total (e.g. "Mode: Cash Total: € 605"), not Sub-Total
        for line in reversed(text.splitlines()):
            stripped = line.strip()
            if not stripped or re.match(r"Sub[-\s]*Total", stripped, re.IGNORECASE):
                continue
            if re.search(r"(?<!Sub[-\s])Total\b", stripped, re.IGNORECASE):
                amt = self._amount_from_line(stripped)
                if amt is not None:
                    extracted["total_amount"] = amt
                    break
            if re.search(r"Total\s*Amount", stripped, re.IGNORECASE):
                amt = self._amount_from_line(stripped)
                if amt is not None:
                    extracted["total_amount"] = amt
                    break

        if extracted["total_amount"] is None:
            m = re.search(
                rf"(?<!Sub[-\s])Total\s*:?\s*{CURRENCY_PREFIX}{AMOUNT}",
                text,
                re.IGNORECASE,
            )
            if m:
                extracted["total_amount"] = float(m.group(1))

        # GST registration number (not tax amount)
        gst_no = re.search(r"GST\s*No[.:]?\s*([A-Z0-9]+)", text, re.IGNORECASE)
        if gst_no:
            extracted["vendor_gst"] = gst_no.group(1).strip()

        # Vendor — prefer first header line with "Kitchen", avoid "'s Kitchen" substring
        if extracted.get("vendor_name"):
            pass
        elif re.search(r"\buber\b", text, re.IGNORECASE):
            extracted["vendor_name"] = "Uber"
        for line in text.splitlines():
            if extracted.get("vendor_name"):
                break
            line = line.strip()
            if re.search(r"kitchen", line, re.IGNORECASE) and len(line) > 6:
                m = re.search(
                    r"([A-Za-z][A-Za-z'\s&]*Kitchen)",
                    line,
                    re.IGNORECASE,
                )
                if m and len(m.group(1)) > 8:
                    name = m.group(1).strip()
                    extracted["vendor_name"] = name
                    extracted["restaurant_name"] = name
                    break

        if not extracted.get("vendor_name"):
            for pattern in (
                r"(Madhuri'?s?\s*Kitchen)",
                r"^([A-Za-z][\w\s&']{4,}Kitchen)\s*$",
            ):
                m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
                if m:
                    extracted["vendor_name"] = m.group(1).strip()
                    extracted["restaurant_name"] = m.group(1).strip()
                    break

        # Re-apply ride fields after generic total/date may have overwritten
        self._parse_ride_receipt(text, extracted)

        # Tax (CGST + SGST lines only; uses subtotal/total for decimal fix)
        tax_total, tax_breakdown = self._parse_gst_tax(
            text,
            subtotal=extracted.get("subtotal"),
            grand_total=extracted.get("total_amount"),
        )
        extracted["tax_breakdown"] = tax_breakdown
        if tax_total is not None:
            extracted["tax_amount"] = tax_total
        elif extracted.get("subtotal") and extracted.get("total_amount"):
            implied = round(extracted["total_amount"] - extracted["subtotal"], 2)
            if 0 < implied < 200:
                extracted["tax_amount"] = implied
                half = round(implied / 2, 2)
                extracted["tax_breakdown"] = {"cgst": half, "sgst": implied - half}

        # Payment mode
        extracted["payment_method"] = self._parse_payment_method(text)

        # Line items
        extracted["items_list"] = self._parse_line_items(text)

        # Confidence score
        score = 0.0
        checks = [
            ("total_amount", 30),
            ("vendor_name", 20),
            ("bill_date", 15),
            ("bill_number", 10),
            ("tax_amount", 10),
            ("payment_method", 10),
            ("pickup_location", 5),
            ("ride_distance", 5),
            ("items_list", 5),
        ]
        for field, weight in checks:
            val = extracted.get(field)
            if val is not None and val != [] and val != {}:
                score += weight
        extracted["confidence_score"] = min(score, 100.0)

        return extracted

    async def extract_bill_data(self, file_path: str, file_type: str) -> Dict[str, Any]:
        return self.extract_bill_data_sync(file_path, file_type)

    def extract_bill_data_sync(self, file_path: str, file_type: str) -> Dict[str, Any]:
        if file_type.lower() == "pdf":
            return self.process_pdf_sync(file_path)
        if file_type.lower() in ["jpg", "jpeg", "png", "webp", "avi"]:
            return self.process_image_sync(file_path)
        raise ValueError(f"Unsupported file type: {file_type}")
