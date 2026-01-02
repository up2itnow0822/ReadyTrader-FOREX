from typing import Dict


def get_pip_value(symbol: str, price: float, lot_size: int = 100000) -> float:
    """
    Calculate the value of 1 pip for a standard lot (or specified lot size).

    Args:
        symbol: e.g. "EURUSD", "USDJPY"
        price: Current exchange rate
        lot_size: Units per lot (default 100k)

    Returns:
        Value of 1 pip in the QUOTE currency.
    """
    sym = symbol.upper().replace("/", "").replace("=X", "")

    # JPY pairs have 2 decimal places, others usually 4
    if "JPY" in sym:
        pip_size = 0.01
    else:
        pip_size = 0.0001

    return pip_size * lot_size


def convert_to_usd(amount: float, quote_currency: str, rates: Dict[str, float]) -> float:
    """
    Convert amount from Quote Currency to USD using provided rates.
    rates map should contain e.g. "EURUSD=X": 1.05, "USDJPY=X": 150.0
    """
    if quote_currency == "USD":
        return amount

    # Direct pair: quote is USD? No, that's base.
    # If quote is JPY, we need USD/JPY rate (or JPY/USD).
    # Typically rates are provided as "EURUSD" (Base=EUR, Quote=USD) -> Price is USD per EUR.
    # "USDJPY" (Base=USD, Quote=JPY) -> Price is JPY per USD.

    # Check for direct pair where Quote is Base of pair
    # Case 1: Convert JPY to USD. Pair is USDJPY. Rate = 150.
    # 1 USD = 150 JPY. 1 JPY = 1/150 USD.
    usd_base_pair = f"USD{quote_currency}=X"
    if usd_base_pair in rates:
        return amount / rates[usd_base_pair]

    # Case 2: Convert EUR to USD. Pair is EURUSD. Rate = 1.05.
    # 1 EUR = 1.05 USD.
    quote_base_pair = f"{quote_currency}USD=X"
    if quote_base_pair in rates:
        return amount * rates[quote_base_pair]

    # Fallback to 1.0 if unknown (mock protection)
    return amount
