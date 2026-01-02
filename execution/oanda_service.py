from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import requests

from execution.base import IBrokerage

logger = logging.getLogger(__name__)


class OandaBrokerage(IBrokerage):
    """
    OANDA v20 REST API Integration.
    Requires OANDA_API_KEY and OANDA_ACCOUNT_ID in environment.
    """

    def __init__(self):
        self.api_key = os.getenv("OANDA_API_KEY")
        self.account_id = os.getenv("OANDA_ACCOUNT_ID")
        self.environment = os.getenv("OANDA_ENVIRONMENT", "practice").lower()

        if self.environment == "live":
            self.base_url = "https://api-fxtrade.oanda.com/v3"
        else:
            self.base_url = "https://api-fxpractice.oanda.com/v3"

        self._available = bool(self.api_key and self.account_id)

    def is_available(self) -> bool:
        return self._available

    def _headers(self):
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def place_order(self, symbol: str, side: str, qty: float, order_type: str = "market", price: Optional[float] = None) -> Dict[str, Any]:
        if not self._available:
            raise RuntimeError("OANDA API not configured (missing OANDA_API_KEY or OANDA_ACCOUNT_ID).")

        # OANDA expects instruments like "EUR_USD"
        oanda_symbol = symbol.replace("/", "_").replace("=X", "")
        if "_" not in oanda_symbol and len(oanda_symbol) == 6:
            oanda_symbol = f"{oanda_symbol[:3]}_{oanda_symbol[3:]}"

        # Units: side + quantity
        units = str(int(qty)) if side.lower() == "buy" else str(int(-qty))

        url = f"{self.base_url}/accounts/{self.account_id}/orders"

        order_data = {
            "order": {
                "units": units,
                "instrument": oanda_symbol,
                "type": "MARKET" if order_type.lower() == "market" else "LIMIT",
                "timeInForce": "FOK" if order_type.lower() == "market" else "GTC",
                "positionFill": "DEFAULT",
            }
        }

        if order_type.lower() == "limit" and price:
            order_data["order"]["price"] = str(price)

        try:
            response = requests.post(url, headers=self._headers(), json=order_data, timeout=10)
            response.raise_for_status()
            data = response.json()

            # Extract transaction ID
            tx_id = data.get("orderFillTransaction", {}).get("id") or data.get("orderCreateTransaction", {}).get("id")

            return {
                "id": str(tx_id),
                "status": "filled" if "orderFillTransaction" in data else "submitted",
                "symbol": symbol,
                "qty": qty,
                "side": side,
                "venue": "oanda",
                "raw": data,
            }
        except Exception as e:
            logger.error(f"OANDA order failed: {e}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            raise RuntimeError(f"OANDA order failure: {str(e)}")

    def get_account_balance(self) -> Dict[str, float]:
        if not self._available:
            raise RuntimeError("OANDA API not configured.")

        url = f"{self.base_url}/accounts/{self.account_id}/summary"
        try:
            response = requests.get(url, headers=self._headers(), timeout=10)
            response.raise_for_status()
            account = response.json().get("account", {})

            return {
                "balance": float(account.get("balance", 0.0)),
                "equity": float(account.get("NAV", 0.0)),
                "margin_used": float(account.get("marginUsed", 0.0)),
                "free_margin": float(account.get("marginAvailable", 0.0)),
                "cash": float(account.get("balance", 0.0)),
            }
        except Exception as e:
            raise RuntimeError(f"OANDA balance fetch failed: {str(e)}")

    def list_positions(self) -> List[Dict[str, Any]]:
        if not self._available:
            raise RuntimeError("OANDA API not configured.")

        url = f"{self.base_url}/accounts/{self.account_id}/positions"
        try:
            response = requests.get(url, headers=self._headers(), timeout=10)
            response.raise_for_status()
            positions_raw = response.json().get("positions", [])

            out = []
            for p in positions_raw:
                # OANDA positions can have both long and short components
                long_units = float(p.get("long", {}).get("units", 0.0))
                short_units = float(p.get("short", {}).get("units", 0.0))
                net_units = long_units + short_units

                if net_units != 0:
                    out.append(
                        {
                            "symbol": p.get("instrument"),
                            "qty": net_units,
                            "avg_price": float(p.get("long", {}).get("averagePrice", 0.0))
                            if net_units > 0
                            else float(p.get("short", {}).get("averagePrice", 0.0)),
                            "unrealized_pnl": float(p.get("unrealizedPL", 0.0)),
                        }
                    )
            return out
        except Exception:
            return []
