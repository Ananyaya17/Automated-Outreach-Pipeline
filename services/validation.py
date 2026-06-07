"""Response validation helpers for API clients."""
from typing import Any, Dict, List, Optional
from utils.logger import get_logger

logger = get_logger(__name__)


class ValidationError(Exception):
    """Raised when API response fails validation."""
    pass


def validate_ocean_company(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate Ocean API company response schema.
    
    Args:
        data: Single company record from Ocean API.
        
    Returns:
        Validated data dict.
        
    Raises:
        ValidationError: If required fields are missing or invalid.
    """
    domain = data.get("domain") or data.get("website")
    name = data.get("name", "")
    
    if not domain or not isinstance(domain, str):
        raise ValidationError(f"Invalid domain in company record: {data}")
    if not isinstance(name, str):
        raise ValidationError(f"Invalid name in company record: {data}")
    
    return {"domain": domain.lower().strip(), "name": name.strip()}


def validate_prospeo_contact(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate Prospeo API contact response schema.
    
    Args:
        data: Single contact record from Prospeo API.
        
    Returns:
        Validated data dict.
        
    Raises:
        ValidationError: If required fields are missing or invalid.
    """
    name = data.get("name") or data.get("full_name", "")
    title = data.get("title", "")
    linkedin = data.get("linkedin")
    
    if not name or not isinstance(name, str):
        raise ValidationError(f"Invalid name in contact record: {data}")
    if not isinstance(title, str):
        raise ValidationError(f"Invalid title in contact record: {data}")
    
    return {
        "name": name.strip(),
        "title": title.strip(),
        "linkedin": linkedin if linkedin is None or isinstance(linkedin, str) else str(linkedin),
    }


def validate_brevo_send(data: Dict[str, Any]) -> bool:
    """Validate Brevo email send response.
    
    Args:
        data: Response from Brevo API.
        
    Returns:
        True if send was accepted, False otherwise.
        
    Raises:
        ValidationError: If response schema is invalid.
    """
    # Brevo returns messageId on success, or an error dict on failure
    if "messageId" in data and isinstance(data.get("messageId"), (int, str)):
        return True
    
    if "code" in data or "message" in data:
        # Error response - not a validation error, just a send failure
        return False
    
    raise ValidationError(f"Unexpected Brevo response schema: {data}")
