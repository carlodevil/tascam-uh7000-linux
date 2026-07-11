"""Best-effort client for the per-user service with safe local fallback."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from .service import BUS_NAME, INTERFACE_NAME, OBJECT_PATH


async def _call_json(method: str, timeout: float) -> dict[str, Any] | None:
    try:
        from dbus_next.aio import MessageBus
    except ImportError:
        return None
    bus = None
    try:
        bus = await asyncio.wait_for(MessageBus().connect(), timeout=timeout)
        introspection = await asyncio.wait_for(
            bus.introspect(BUS_NAME, OBJECT_PATH), timeout=timeout
        )
        proxy = bus.get_proxy_object(BUS_NAME, OBJECT_PATH, introspection)
        interface = proxy.get_interface(INTERFACE_NAME)
        caller = getattr(interface, f"call_{_camel_to_snake(method)}")
        payload = await asyncio.wait_for(caller(), timeout=timeout)
        return json.loads(payload)
    except Exception:
        return None
    finally:
        if bus is not None:
            bus.disconnect()


def _camel_to_snake(name: str) -> str:
    output: list[str] = []
    for index, character in enumerate(name):
        if character.isupper() and index:
            output.append("_")
        output.append(character.lower())
    return "".join(output)


def service_state(method: str = "GetState", timeout: float = 0.75) -> dict[str, Any] | None:
    try:
        return asyncio.run(_call_json(method, timeout))
    except (RuntimeError, OSError):
        return None
