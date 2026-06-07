"""Logging utilities with PII masking."""
import re
import logging


def mask_pii(text: str) -> str:
    """Mask email addresses and common PII patterns in log output.
    
    Args:
        text: Text that may contain PII.
        
    Returns:
        Text with emails masked as user@***.
    """
    if not isinstance(text, str):
        return str(text)
    # Replace email addresses with masked version
    text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', 'user@***.***', text)
    return text


class PIIMaskingFormatter(logging.Formatter):
    """Log formatter that masks PII in log messages."""
    
    def format(self, record):
        # Format the log record normally
        msg = super().format(record)
        # Mask PII in the formatted message
        msg = mask_pii(msg)
        return msg


def setup_pii_masking_for_handler(handler: logging.Handler):
    """Apply PII masking formatter to an existing handler."""
    formatter = PIIMaskingFormatter(
        fmt='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)
