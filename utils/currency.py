#!/usr/bin/env python3
"""
Currency conversion utilities
"""
import httpx
import asyncio
import logging

logger = logging.getLogger(__name__)

async def get_usd_to_irr_rate() -> float:
    """
    Get current USD to IRR exchange rate from a free API.
    Returns the rate or a fallback rate if API fails.
    
    Returns:
        float: USD to IRR rate
    """
    fallback_rate = 42000.0  # Fallback rate if API fails
    
    apis_to_try = [
        # Free APIs for USD to IRR
        {
            "url": "https://api.exchangerate-api.com/v4/latest/USD",
            "parser": lambda data: data.get("rates", {}).get("IRR", fallback_rate)
        },
        {
            "url": "https://api.fixer.io/latest?base=USD&symbols=IRR",
            "parser": lambda data: data.get("rates", {}).get("IRR", fallback_rate)
        },
        {
            "url": "https://open.er-api.com/v6/latest/USD",
            "parser": lambda data: data.get("rates", {}).get("IRR", fallback_rate)
        }
    ]
    
    for api in apis_to_try:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(api["url"])
                if response.status_code == 200:
                    data = response.json()
                    rate = api["parser"](data)
                    if rate and rate > 0:
                        logger.info(f"Got USD to IRR rate: {rate}")
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