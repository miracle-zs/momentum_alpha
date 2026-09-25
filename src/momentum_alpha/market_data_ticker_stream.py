from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import threading
from typing import Any, Callable

from momentum_alpha.structured_log import emit_structured_log


BINANCE_FSTREAM_MINI_TICKER_WS_URL = "wss://fstream.binance.com/ws/!miniTicker@arr"
BINANCE_TESTNET_FSTREAM_MINI_TICKER_WS_URL = "wss://stream.binancefuture.com/ws/!miniTicker@arr"


@dataclass(frozen=True)
class MiniTickerUpdate:
    symbol: str
    close_price: Decimal
    open_price: Decimal | None
    high_price: Decimal | None
    low_price: Decimal | None
    observed_at: datetime


def parse_mini_ticker_update(payload: object) -> MiniTickerUpdate | None:
    if not isinstance(payload, dict):
        return None
    event_type = str(payload.get("e") or "").lower()
    if event_type and event_type != "24hrminiticker":
        return None
    symbol = str(payload.get("s") or "").upper()
    if not symbol:
        return None

    try:
        close_price = Decimal(str(payload.get("c")))
        if not close_price.is_finite() or close_price <= Decimal("0"):
            return None
    except (InvalidOperation, TypeError, ValueError):
        return None

    def _parse_opt_decimal(val: object) -> Decimal | None:
        try:
            d = Decimal(str(val))
            return d if d.is_finite() else None
        except (InvalidOperation, TypeError, ValueError):
            return None

    open_price = _parse_opt_decimal(payload.get("o"))
    high_price = _parse_opt_decimal(payload.get("h"))
    low_price = _parse_opt_decimal(payload.get("l"))

    event_time_ms = payload.get("E")
    if event_time_ms is not None:
        try:
            observed_at = datetime.fromtimestamp(int(event_time_ms) / 1000, tz=timezone.utc)
        except (ValueError, TypeError, OSError):
            observed_at = datetime.now(timezone.utc)
    else:
        observed_at = datetime.now(timezone.utc)

    return MiniTickerUpdate(
        symbol=symbol,
        close_price=close_price,
        open_price=open_price,
        high_price=high_price,
        low_price=low_price,
        observed_at=observed_at,
    )


def parse_mini_ticker_updates(payload: object) -> list[MiniTickerUpdate]:
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        items = payload["data"]
    elif isinstance(payload, list):
        items = payload
    else:
        return []

    updates: list[MiniTickerUpdate] = []
    for item in items:
        update = parse_mini_ticker_update(item)
        if update is not None:
            updates.append(update)
    return updates


@dataclass
class MiniTickerStreamHandle:
    stop_event: threading.Event
    thread: threading.Thread

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=2.0)


def _default_mini_ticker_websocket_runner(
    *,
    url: str,
    on_message: Callable[[Any], None],
    stop_event: threading.Event,
    logger=None,
) -> None:
    try:
        import websocket
    except ImportError as exc:
        raise RuntimeError("websocket-client is required for mini ticker streaming") from exc

    app = websocket.WebSocketApp(
        url,
        on_message=lambda _app, message: on_message(message),
    )

    def _close_when_stopped() -> None:
        while not stop_event.is_set():
            if stop_event.wait(0.25):
                break
        app.close()

    threading.Thread(target=_close_when_stopped, daemon=True).start()
    app.run_forever(ping_interval=30, ping_timeout=10)


@dataclass
class MiniTickerStream:
    on_updates: Callable[[list[MiniTickerUpdate]], None]
    testnet: bool = False
    logger: object | None = None
    websocket_runner: Callable[..., None] | None = None
    reconnect_delay_seconds: float = 3.0

    def _log(self, event: str, *, level: str = "INFO", **fields: object) -> None:
        if self.logger is not None:
            emit_structured_log(
                self.logger,
                service="mini-ticker-stream",
                event=event,
                level=level,
                **fields,
            )

    def start(self) -> MiniTickerStreamHandle:
        stop_event = threading.Event()
        thread = threading.Thread(target=self.run_forever, kwargs={"stop_event": stop_event}, daemon=True)
        thread.start()
        return MiniTickerStreamHandle(stop_event=stop_event, thread=thread)

    def run_forever(self, *, stop_event: threading.Event) -> None:
        url = (
            BINANCE_TESTNET_FSTREAM_MINI_TICKER_WS_URL
            if self.testnet
            else BINANCE_FSTREAM_MINI_TICKER_WS_URL
        )

        def _on_message(raw_message: Any) -> None:
            try:
                payload = json.loads(raw_message) if isinstance(raw_message, (str, bytes)) else raw_message
            except (TypeError, ValueError):
                return
            updates = parse_mini_ticker_updates(payload)
            if updates:
                self.on_updates(updates)

        runner = self.websocket_runner or _default_mini_ticker_websocket_runner

        while not stop_event.is_set():
            try:
                self._log("connecting", url=url)
                runner(
                    url=url,
                    on_message=_on_message,
                    stop_event=stop_event,
                    logger=self.logger,
                )
            except Exception as exc:
                self._log("stream-error", level="WARNING", error=str(exc))

            if stop_event.wait(self.reconnect_delay_seconds):
                break
