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