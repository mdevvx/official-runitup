import re
from typing import Optional


def validate_url(url: str) -> bool:
    """Validate URL format"""
    url_pattern = re.compile(
        r"^https?://"  # http:// or https://
        r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|"  # domain...
        r"localhost|"  # localhost...
        r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"  # ...or ip
        r"(?::\d+)?"  # optional port
        r"(?:/?|[/?]\S+)$",
        re.IGNORECASE,
    )

    return url_pattern.match(url) is not None


def validate_amount(amount: str) -> Optional[float]:
    """Validate and parse amount"""
    try:
        # Remove currency symbols and commas
        cleaned = amount.replace("$", "").replace(",", "").strip()
        value = float(cleaned)

        if value < 0:
            return None

        return round(value, 2)
    except (ValueError, AttributeError):
        return None


def sanitize_input(text: str, max_length: int = 1000) -> str:
    """Sanitize user input"""
    # Remove mentions
    text = re.sub(r"<@!?\d+>", "", text)
    text = re.sub(r"<@&\d+>", "", text)
    text = re.sub(r"<#\d+>", "", text)

    # Truncate
    if len(text) > max_length:
        text = text[:max_length]

    return text.strip()
