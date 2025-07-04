import logging
import traceback
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

def log_exception(
    exception: Exception,
    context: Optional[Dict[str, Any]] = None,
    user_id: Optional[int] = None,
    event_id: Optional[int] = None,
    message: Optional[str] = None
) -> None:
    """
    Log an exception with context information.
    
    Args:
        exception: The exception to log
        context: Additional context information as a dictionary
        user_id: The ID of the user who triggered the exception
        event_id: The ID of the event related to the exception
        message: Additional message to include in the log
    """
    # Create a dictionary with all context information
    log_context = {
        "exception_type": type(exception).__name__,
        "exception_message": str(exception),
        "traceback": traceback.format_exc()
    }
    
    # Add user_id if provided
    if user_id is not None:
        log_context["user_id"] = user_id
    
    # Add event_id if provided
    if event_id is not None:
        log_context["event_id"] = event_id
    
    # Add additional context if provided
    if context is not None:
        log_context.update(context)
    
    # Create log message
    log_message = f"Exception: {type(exception).__name__}"
    
    if user_id is not None:
        log_message += f", User ID: {user_id}"
    
    if event_id is not None:
        log_message += f", Event ID: {event_id}"
    
    if message is not None:
        log_message += f", Message: {message}"
    
    # Log the exception with context
    logger.error(log_message, exc_info=True, extra={"context": log_context})