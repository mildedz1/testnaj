#!/usr/bin/env python3
"""
Currency conversion utilities
"""
import httpx
import asyncio
import logging
import os

logger = logging.getLogger(__name__)

# Manual exchange rate (can be set via environment variable)
MANUAL_USD_IRR_RATE = float(os.getenv("USD_IRR_RATE", "92500"))

async def get_usd_to_irr_rate() -> float:
    """
    Get current USD to IRR exchange rate from a free API.
    Returns the rate or a fallback rate if API fails.
    
    Returns:
        float: USD to IRR rate
    """
    fallback_rate = 92500.0  # Updated fallback rate based on navasan API
    
    apis_to_try = [
        # Primary API with your exact specification
        {
            "url": "http://api.navasan.tech/latest/?api_key=freeZLXIEWtrCyqbttzJWnPvKx8OC832",
            "parser": lambda data: float(data.get("usd_buy", {}).get("value", fallback_rate)) if isinstance(data, dict) and data.get("usd_buy") and isinstance(data.get("usd_buy"), dict) else fallback_rate
        },
        # Backup APIs
        {
            "url": "https://api.currencyapi.com/v3/latest?apikey=cur_live_bFJ93gF5X2HLQrFWlq36iaDLi9F6rFb2jYzCMtSu&currencies=IRR&base_currency=USD",
            "parser": lambda data: float(data.get("data", {}).get("IRR", {}).get("value", fallback_rate)) if isinstance(data, dict) else fallback_rate
        },
        # International rate with multiplier
        {
            "url": "https://api.exchangerate-api.com/v4/latest/USD", 
            "parser": lambda data: float(data.get("rates", {}).get("IRR", 0)) * 1.7 if data.get("rates", {}).get("IRR") and float(data.get("rates", {}).get("IRR", 0)) > 0 else fallback_rate
        },
        # Manual rate as last resort
        {
            "url": "manual",
            "parser": lambda data: MANUAL_USD_IRR_RATE  # Can be set via USD_IRR_RATE environment variable
        }
    ]
    
    for api in apis_to_try:
        try:
            # Handle manual rate
            if api["url"] == "manual":
                rate = api["parser"](None)
                if rate and rate > 0:
                    logger.info(f"Using manual USD to IRR rate: {rate}")
                    return float(rate)
                continue
            
            # Handle API calls
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(api["url"])
                if response.status_code == 200:
                    data = response.json()
                    rate = api["parser"](data)
                    if rate and rate > 0:
                        logger.info(f"Got USD to IRR rate from {api['url']}: {rate}")
                        return float(rate)
        except Exception as e:
            logger.warning(f"Failed to get rate from {api['url']}: {e}")
            continue
    
    logger.warning(f"All APIs failed, using fallback rate: {fallback_rate}")
    return fallback_rate


async def convert_irr_to_usd(irr_amount: int) -> tuple[float, float]:
    """
    Convert Iranian Rial to USD.
    
    Args:
        irr_amount: Amount in Iranian Rial
        
    Returns:
        tuple: (usd_amount, exchange_rate_used)
    """
    rate = await get_usd_to_irr_rate()
    usd_amount = irr_amount / rate
    return round(usd_amount, 2), rate


def format_currency_info(irr_amount: int, usd_amount: float, rate: float) -> str:
    """
    Format currency conversion info for display.
    
    Args:
        irr_amount: Amount in IRR
        usd_amount: Amount in USD
        rate: Exchange rate used
        
    Returns:
        Formatted string with currency info
    """
    return (
        f"💰 <b>مبلغ:</b> {irr_amount:,} تومان\n"
        f"💵 <b>معادل:</b> ${usd_amount:.2f} USD\n"
        f"📊 <b>نرخ روز:</b> {rate:,.0f} ریال به ازای هر دلار"
    )


async def test_currency_api():
    """Test function to check if currency API is working."""
    try:
        rate = await get_usd_to_irr_rate()
        print(f"Current USD to IRR rate: {rate}")
        
        # Test conversion
        test_amount = 100000  # 100,000 Toman
        usd_amount, used_rate = await convert_irr_to_usd(test_amount)
        print(f"{test_amount:,} Toman = ${usd_amount:.2f} USD (Rate: {used_rate:,.0f})")
        
        return True
    except Exception as e:
        print(f"Currency API test failed: {e}")
        return False


if __name__ == "__main__":
    # Test the currency API
    asyncio.run(test_currency_api())