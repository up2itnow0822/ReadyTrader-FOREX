from __future__ import annotations

import importlib
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Type

from .providers import MarketDataProvider


@dataclass(frozen=True)
class ProviderSpec:
    """
    Configuration for an external MarketDataProvider plugin.

    Example env:
    MARKETDATA_PLUGINS_JSON='[{"class":"marketdata.plugin_examples:StaticJsonFileProvider","provider_id":"file_feed","kwargs":{"path":"/data/feed.json"}}]'
    """

    class_path: str
    provider_id: Optional[str] = None
    kwargs: Optional[Dict[str, Any]] = None


def _parse_plugins_env() -> List[ProviderSpec]:
    raw = (os.getenv("MARKETDATA_PLUGINS_JSON") or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception as e:
        raise ValueError(f"Invalid MARKETDATA_PLUGINS_JSON: {e}") from e
    if not isinstance(data, list):
        raise ValueError("MARKETDATA_PLUGINS_JSON must be a JSON list")
    specs: List[ProviderSpec] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        cls = str(item.get("class") or "").strip()
        if not cls:
            continue
        specs.append(
            ProviderSpec(
                class_path=cls,
                provider_id=str(item.get("provider_id") or "").strip() or None,
                kwargs=item.get("kwargs") if isinstance(item.get("kwargs"), dict) else None,
            )
        )
    return specs


def _load_class(path: str) -> Type[Any]:
    """
    Load a class from 'module:ClassName' format.
    """
    if ":" not in path:
        raise ValueError("Plugin class must be in 'module:ClassName' format")
    module_name, cls_name = path.split(":", 1)
    mod = importlib.import_module(module_name)
    cls = getattr(mod, cls_name, None)
    if cls is None:
        raise ValueError(f"Could not find class {cls_name} in module {module_name}")
    return cls


def load_marketdata_plugins() -> List[MarketDataProvider]:
    """
    Load external market data providers configured by env.
    """
    providers: List[MarketDataProvider] = []
    for spec in _parse_plugins_env():
        cls = _load_class(spec.class_path)
        kwargs = spec.kwargs or {}
        inst = cls(**kwargs)
        if not hasattr(inst, "fetch_ticker"):
            raise ValueError(f"Plugin {spec.class_path} does not implement fetch_ticker")
        if not hasattr(inst, "fetch_ohlcv"):
            raise ValueError(f"Plugin {spec.class_path} does not implement fetch_ohlcv")
        if spec.provider_id:
            setattr(inst, "provider_id", spec.provider_id)
        # Ensure provider_id exists
        if not getattr(inst, "provider_id", ""):
            raise ValueError(f"Plugin {spec.class_path} must define provider_id or set provider_id in config")
        providers.append(inst)
    return providers
