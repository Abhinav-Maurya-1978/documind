import re
from datetime import datetime
from typing import Any, Dict, Optional, Tuple
from dateutil import parser as date_parser

class ValueNormalizer:
    """Deterministic normalizer for monetary values, dates, quantities, and terms."""

    CURRENCY_SYMBOLS = {
        "₹": "INR",
        "rs": "INR",
        "rs.": "INR",
        "inr": "INR",
        "rupees": "INR",
        "$": "USD",
        "usd": "USD",
        "€": "EUR",
        "eur": "EUR",
        "£": "GBP",
        "gbp": "GBP",
        "¥": "JPY",
        "jpy": "JPY",
    }

    @classmethod
    def normalize_monetary(cls, raw_val: str) -> Dict[str, Any]:
        """
        Extracts currency and numeric value from monetary strings.
        Supports: '₹50,000', 'Rs. 55,000.00', '$ 1,200', 'USD 500', '1,50,000 INR'.
        """
        text = raw_val.strip()
        currency = None

        # Check for currency symbols or names
        lower_text = text.lower()
        for sym, code in cls.CURRENCY_SYMBOLS.items():
            pattern = rf"(?:\b|\A){re.escape(sym)}(?:\b|\Z|\s*)" if len(sym) > 1 else re.escape(sym)
            if re.search(pattern, lower_text):
                currency = code
                break

        # Extract numeric string
        # Match numbers with commas, periods
        num_match = re.search(r"[-+]?[0-9]{1,3}(?:[,\s][0-9]{2,3})*(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?", text)
        if not num_match:
            return {"normalized": None, "currency": currency, "valid": False}

        num_str = num_match.group(0).replace(",", "").replace(" ", "")
        try:
            val = float(num_str)
            return {
                "normalized": val,
                "currency": currency or "UNKNOWN",
                "valid": True,
            }
        except ValueError:
            return {"normalized": None, "currency": currency, "valid": False}

    @classmethod
    def normalize_date(cls, raw_val: str) -> Dict[str, Any]:
        """
        Parses date into ISO 'YYYY-MM-DD' and flags ambiguity when numeric format is ambiguous
        (e.g., 01/02/2026 vs Feb 1, 2026).
        """
        text = raw_val.strip()
        is_ambiguous = False
        parsed_iso = None

        # Check for pure numeric slash/dash date: DD/MM/YYYY or MM/DD/YYYY
        num_date_match = re.search(r"\b(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{2,4})\b", text)
        if num_date_match:
            part1 = int(num_date_match.group(1))
            part2 = int(num_date_match.group(2))
            year = int(num_date_match.group(3))
            if year < 100:
                year += 2000

            # If both parts <= 12, interpretation is ambiguous (could be DD/MM or MM/DD)
            if 1 <= part1 <= 12 and 1 <= part2 <= 12:
                is_ambiguous = True
                # Default assume DD/MM/YYYY (standard in procurement/international), but flag ambiguity
                try:
                    dt = datetime(year, part2, part1)
                    parsed_iso = dt.strftime("%Y-%m-%d")
                except ValueError:
                    dt = datetime(year, part1, part2)
                    parsed_iso = dt.strftime("%Y-%m-%d")
            elif part1 > 12 >= part2:
                # Part1 must be day
                try:
                    dt = datetime(year, part2, part1)
                    parsed_iso = dt.strftime("%Y-%m-%d")
                except ValueError:
                    pass
            elif part2 > 12 >= part1:
                # Part2 must be day
                try:
                    dt = datetime(year, part1, part2)
                    parsed_iso = dt.strftime("%Y-%m-%d")
                except ValueError:
                    pass

        if not parsed_iso:
            try:
                # Use dateutil parser for textual dates like "February 1, 2026"
                dt = date_parser.parse(text, fuzzy=True, dayfirst=True)
                parsed_iso = dt.strftime("%Y-%m-%d")
            except Exception:
                return {"normalized": None, "is_ambiguous": False, "valid": False}

        return {
            "normalized": parsed_iso,
            "is_ambiguous": is_ambiguous,
            "valid": True,
        }

    @classmethod
    def normalize_quantity(cls, raw_val: str) -> Dict[str, Any]:
        """
        Extracts quantity count and unit from expressions like '10 laptops', '25 units', '50 kg'.
        """
        text = raw_val.strip()
        match = re.search(r"(\d+(?:\.\d+)?)\s*([a-zA-Z]+)?", text)
        if not match:
            return {"normalized": None, "unit": None, "valid": False}

        qty = float(match.group(1))
        unit = match.group(2).lower() if match.group(2) else "units"
        return {
            "normalized": qty,
            "unit": unit,
            "valid": True,
        }

    @classmethod
    def normalize_deadline(cls, raw_val: str) -> Dict[str, Any]:
        """
        Normalizes deadlines such as 'within 30 days', '30 days from PO', 'Net 30', '45 days'.
        """
        text = raw_val.strip().lower()
        days_match = re.search(r"(\d+)\s*(?:business\s*)?days", text)
        if days_match:
            return {"days": int(days_match.group(1)), "type": "days", "valid": True}

        net_match = re.search(r"net\s*(\d+)", text)
        if net_match:
            return {"days": int(net_match.group(1)), "type": "net_days", "valid": True}

        if "immediate" in text or "upon receipt" in text or "on delivery" in text:
            return {"days": 0, "type": "immediate", "valid": True}

        return {"days": None, "type": "unspecified", "valid": False}

    @classmethod
    def normalize_identifier(cls, raw_val: str) -> str:
        """Standardizes document IDs (e.g., 'PO-2024-001' vs 'PO 2024 001' -> 'PO2024001')."""
        return re.sub(r"[\s\-_/]", "", raw_val).upper()
