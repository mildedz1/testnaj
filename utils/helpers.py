#!/usr/bin/env python3
"""
Utility functions and helpers
"""
from aiogram.types import CallbackQuery


async def safe_callback_answer(callback: CallbackQuery, text: str, show_alert: bool = False, max_length: int = 200):
    """
    Safely answer callback queries with length checking to avoid MESSAGE_TOO_LONG errors.
    
    Args:
        callback: The CallbackQuery object
        text: The text to send
        show_alert: Whether to show as alert
        max_length: Maximum allowed length (default 200, Telegram limit is around 200)
    """
    if len(text) > max_length:
        truncated_text = text[:max_length-3] + "..."
        await callback.answer(truncated_text, show_alert=show_alert)
    else:
        await callback.answer(text, show_alert=show_alert)


def truncate_error(error: Exception, max_length: int = 100) -> str:
    """
    Safely truncate error message to avoid too long messages.
    
    Args:
        error: The exception object
        max_length: Maximum length for error message
        
    Returns:
        Truncated error message
    """
    error_str = str(error)
    if len(error_str) > max_length:
        return error_str[:max_length-3] + "..."
    return error_str


def convert_unlimited_for_display(value: int) -> str:
    """
    Convert -1 (unlimited) to نامحدود for display purposes.
    
    Args:
        value: The numeric value
        
    Returns:
        "نامحدود" if value is -1, otherwise str(value)
    """
    return "نامحدود" if value == -1 else str(value)


def convert_unlimited_for_api(value: int, large_number: int = 999999999) -> int:
    """
    Convert -1 (unlimited) to a very large number for API calls.
    This is needed because some APIs don't accept -1 but need a large number instead.
    
    Args:
        value: The numeric value
        large_number: The large number to use instead of -1
        
    Returns:
        large_number if value is -1, otherwise the original value
    """
    return large_number if value == -1 else value


def format_traffic_display(bytes_value: int) -> str:
    """
    Format traffic for display with unlimited handling.
    
    Args:
        bytes_value: Traffic in bytes (-1 for unlimited)
        
    Returns:
        Formatted string for display
    """
    if bytes_value == -1:
        return "نامحدود"
    
    # Convert bytes to GB for display
    gb_value = bytes_value / (1024 ** 3)
    return f"{gb_value:.1f} GB"


def format_time_display(seconds_value: int) -> str:
    """
    Format time for display with unlimited handling.
    
    Args:
        seconds_value: Time in seconds (-1 for unlimited)
        
    Returns:
        Formatted string for display
    """
    if seconds_value == -1:
        return "نامحدود"
    
    # Convert seconds to days for display
    days_value = seconds_value / 86400
    return f"{days_value:.1f} روز"