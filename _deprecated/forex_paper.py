from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from app.core.config import settings
from common.forex_math import convert_to_usd
from execution.base import IBrokerage
from marketdata.exchange_provider import ExchangeProvider

logger = logging.getLogger(__name__)


class ForexPaperBrokerage(IBrokerage):
    """
    Paper brokerage for Forex trading with Margin and Leverage.
    """

    def __init__(self, exchange_provider: Optional[ExchangeProvider] = None):
        self.exchange_provider = exchange_provider or ExchangeProvider()
        # Balance = Cash + Realized PnL
        self.balance = 100_000.0
        # Equity = Balance + Unrealized PnL
        self.equity = 100_000.0
        # Used Margin = (Position Value / Leverage)
        self.margin_used = 0.0
        self.free_margin = 100_000.0

        self.positions: Dict[str, Dict[str, Any]] = {}
        self.orders: List[Dict[str, Any]] = []
        self._available = True

    def is_available(self) -> bool:
        return self._available

    def _get_price(self, symbol: str) -> float:
        try:
            ticker = self.exchange_provider.fetch_ticker(symbol)
            price = ticker.get("last") or ticker.get("close")
            if not price:
                raise ValueError("Price unavailable")
            return float(price)
        except Exception as e:
            # Try simple fallback if ticker fails (e.g. during test)
            raise RuntimeError(f"Could not fetch price for {symbol}: {e}")

    def place_order(self, symbol: str, side: str, qty: float, order_type: str = "market", price: Optional[float] = None) -> Dict[str, Any]:
        """
        Execute a paper order.
        """
        symbol = symbol.upper()
        # Ensure we have price
        execute_price = price if (order_type == "limit" and price) else self._get_price(symbol)

        # Calculate Margin Required
        # Value = qty * price (if base is USD? No, Value in USD)
        # We need standard notation: EURUSD -> Base EUR.
        # Contract Size = qty (units).
        # Contract Value in USD = qty * price (if Quote is USD, e.g. EURUSD).
        # If USDJPY, Contract Value in USD = qty. (Since Base is USD).
        # We need a robust "Get Value in USD" function.

        # Simplified: Assume Quote is USD for calculation or convert.
        # But wait, margin is based on Notion Value in Account Currency (USD).

        # Conversion Logic:
        # Base/Quote.
        # If Base == USD (USDJPY), Value = qty (USD).
        # If Quote == USD (EURUSD), Value = qty * price (USD).
        # Else (EURGBP), Value = qty * (EURUSD Rate).

        # For Phase 1, we implement a helper to get USD Value of the POSITION.
        base_currency = symbol[:3]

        # Get rate for Base -> USD
        if base_currency == "USD":
            usd_value = qty
        else:
            # Need rate for BaseUSD
            # Try to fetch it? Or derive from current price if Quote is USD
            if symbol.endswith("USD") or symbol.endswith("USD=X"):
                usd_value = qty * execute_price
            else:
                # Complicated cross-pair.
                # Let's try to fetch BaseUSD
                try:
                    rate = self._get_price(f"{base_currency}USD=X")
                    usd_value = qty * rate
                except Exception:
                    # Fallback assumption for mocks
                    usd_value = qty * execute_price  # Inaccurate but functional for now

        margin_required = usd_value / settings.LEVERAGE

        self._update_account_state()

        if side.lower() == "buy":
            # Check Margin
            if self.free_margin < margin_required:
                raise RuntimeError(f"Insufficient free margin. Required: ${margin_required:.2f}, Free: ${self.free_margin:.2f}")

            # New Position or Add
            if symbol not in self.positions:
                self.positions[symbol] = {
                    "symbol": symbol,
                    "qty": 0.0,
                    "avg_price": 0.0,
                    "side": "buy",  # Simplified netting
                }

            p = self.positions[symbol]
            current_qty = p["qty"]
            new_qty = current_qty + qty
            p["avg_price"] = ((p["avg_price"] * current_qty) + (execute_price * qty)) / new_qty
            p["qty"] = new_qty

        else:  # SELL
            # For simplicity, we only allow closing or flipping via netting in this version,
            # OR we track short positions (neg qty).
            # Let's use Signed Qty: +Buy, -Sell.

            # Re-eval logic for signed quantity
            # If current is long (+), sell reduces.
            # If current is 0, sell makes short (-).

            # Check margin for Short? Same logic.
            if self.free_margin < margin_required:
                raise RuntimeError("Insufficient free margin for Short.")

            if symbol not in self.positions:
                self.positions[symbol] = {"symbol": symbol, "qty": 0.0, "avg_price": 0.0}

            p = self.positions[symbol]
            # Netting logic
            # If we are long 100k @ 1.05 and sell 50k @ 1.06 -> Realize Profit on 50k. Remaining 50k @ 1.05.
            # If we sell 150k -> Realize Profit on 100k. New Short 50k @ 1.06.

            # Simplify: Just update signed qty and simple avg price?
            # No, Closing requires Realizing PnL.

            # If Flat or Short, just add to short position
            if p["qty"] <= 0:
                current_qty = abs(p["qty"])
                new_qty = current_qty + qty
                # Weighted avg for short entry
                p["avg_price"] = ((p["avg_price"] * current_qty) + (execute_price * qty)) / new_qty
                p["qty"] -= qty  # More negative

            else:
                # Closing Long
                closing_qty = min(p["qty"], qty)
                remaining_qty = p["qty"] - qty

                # Realize PnL on closing_qty
                # (Sell Price - Entry Price) * qty * (USD per Quote Unit? No, depends on Pip Value)
                # Profit = (Price_Diff) * Qty
                # If EURUSD: (1.06 - 1.05) * 50,000 = 0.01 * 50,000 = $500.

                diff = execute_price - p["avg_price"]
                # Convert this price diff to USD value
                # Using our helper
                # For EURUSD (Quote USD), value is direct.
                # For USDJPY (Quote JPY), diff is in JPY. Convert to USD.

                quote_curr = symbol[3:6]
                raw_pnl = diff * closing_qty

                # Convert raw_pnl (in Quote) to USD
                # Need current rates map for conversion
                # We can fetch just the needed pair
                rates = {}
                if quote_curr != "USD":
                    try:
                        rates[f"USD{quote_curr}=X"] = self._get_price(f"USD{quote_curr}=X")
                    except Exception as e:
                        logger.debug(f"Failed to fetch USD{quote_curr}=X: {e}")

                usd_pnl = convert_to_usd(raw_pnl, quote_curr, rates)

                self.balance += usd_pnl
                p["qty"] = remaining_qty

                # If we flipped to net short
                if remaining_qty < 0:
                    p["avg_price"] = execute_price  # New entry for the short portion
                    p["qty"] = remaining_qty

        order_id = str(uuid.uuid4())
        order = {
            "id": order_id,
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "price": execute_price,
            "status": "filled",
            "type": order_type,
            "timestamp": time.time(),
        }
        self.orders.append(order)
        self._update_account_state()

        return order

    def _update_account_state(self):
        # Recalculate Equity and Margin
        float_pnl = 0.0
        used_margin = 0.0

        for sym, data in self.positions.items():
            qty = data["qty"]
            if qty == 0:
                continue

            try:
                current_price = self._get_price(sym)
            except Exception:
                current_price = data["avg_price"]

            # Unrealized PnL
            diff = current_price - data["avg_price"]
            if qty < 0:  # Short
                diff = data["avg_price"] - current_price

            raw_pnl = diff * abs(qty)
            quote_curr = sym[3:6]
            rates = {}
            # Optimally we batch fetch rates, for now ad-hoc
            if quote_curr != "USD":
                try:
                    rates[f"USD{quote_curr}=X"] = self._get_price(f"USD{quote_curr}=X")
                except Exception as e:
                    logger.debug(f"Failed to fetch USD{quote_curr}=X: {e}")

            usd_pnl = convert_to_usd(raw_pnl, quote_curr, rates)
            data["unrealized_pnl"] = usd_pnl
            float_pnl += usd_pnl

            # Margin Used
            # Base Value in USD / Leverage
            base_curr = sym[:3]
            base_val = 0.0
            if base_curr == "USD":
                base_val = abs(qty)
            else:
                # Try BaseUSD
                if sym.endswith("USD") or sym.endswith("USD=X"):
                    base_val = abs(qty) * current_price
                else:
                    # Approx
                    base_val = abs(qty) * current_price

            used_margin += base_val / settings.LEVERAGE

        self.equity = self.balance + float_pnl
        self.margin_used = used_margin
        self.free_margin = self.equity - self.margin_used

    def get_account_balance(self) -> Dict[str, float]:
        self._update_account_state()
        return {
            "balance": self.balance,
            "equity": self.equity,
            "margin_used": self.margin_used,
            "free_margin": self.free_margin,
            "cash": self.free_margin,  # Backward compatibility API
            "buying_power": self.free_margin * settings.LEVERAGE,
        }

    def list_positions(self) -> List[Dict[str, Any]]:
        self._update_account_state()
        out = []
        for sym, data in self.positions.items():
            if data["qty"] == 0:
                continue
            out.append({"symbol": sym, "qty": data["qty"], "avg_price": data["avg_price"], "unrealized_pnl": data.get("unrealized_pnl", 0.0)})
        return out
