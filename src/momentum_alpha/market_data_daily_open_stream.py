from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation

from momentum_alpha.structured_log import emit_structured_log


BINANCE_FSTREAM_MARKET_WS_URL = "wss://fstream.binance.com/ws"
BINANCE_TESTNET_FSTREAM_MARKET_WS_URL = "wss://stream.binancefuture.com/ws"


@dataclass(frozen=True)
class DailyOpenUpdate:
    symbol: str
    trading_day: date
    open_price: Decimal
    observed_at: datetime


def parse_daily_open_update(payload: object) -> DailyOpenUpdate | None:
    if not isinstance(payload, dict):
        return None
    if isinstance(payload.get("data"), dict):
        payload = payload["data"]
    if str(payload.get("e") or "").lower() != "kline":
        return None
    kline = payload.get("k")
    if not isinstance(kline, dict) or str(kline.get("i") or "") != "1d":
        return None
    symbol = str(payload.get("s") or kline.get("s") or "").upper()
    if not symbol:
        return None
    try:
        open_price = Decimal(str(kline.get("o")))
        open_time = datetime.fromtimestamp(int(kline.get("t")) / 1000, tz=timezone.utc)
        event_time = datetime.fromtimestamp(
            int(payload.get("E") or kline.get("T") or kline.get("t")) / 1000,
            tz=timezone.utc,
        )
    except (InvalidOperation, TypeError, ValueError, OSError):
        return None
    if not open_price.is_finite() or open_price <= Decimal("0"):
        return None
    return DailyOpenUpdate(
        symbol=symbol,
        trading_day=open_time.date(),
        open_price=open_price,
        observed_at=event_time,
    )


def _seconds_until_capture_window(now: datetime) -> float:
    now_utc = now.astimezone(timezone.utc)
    window_start = datetime.combine(now_utc.date(), time(23, 58), tzinfo=timezone.utc)
    window_end = datetime.combine(now_utc.date(), time(0, 10), tzinfo=timezone.utc)
    if now_utc.time() <= time(0, 10):
        return 0
    if now_utc < window_start:
        return max(0.0, (window_start - now_utc).total_seconds())
    return 0


def _capture_deadline(now: datetime) -> datetime:
    now_utc = now.astimezone(timezone.utc)
    target_day = now_utc.date() + (timedelta(days=1) if now_utc.time() >= time(23, 58) else timedelta())
    return datetime.combine(target_day, time(0, 10), tzinfo=timezone.utc)


@dataclass
class DailyOpenKlineStream:
    symbols: tuple[str, ...]
    on_update: object
    testnet: bool = False
    logger: object | None = None
    now_provider: object = lambda: datetime.now(timezone.utc)
    websocket_runner: object | None = None
    reconnect_delay_seconds: int = 5

    def _log(self, event: str, *, level: str = "INFO", **fields: object) -> None:
        if self.logger is not None:
            emit_structured_log(
                self.logger,
                service="daily-open-stream",
                event=event,
                level=level,
                **fields,
            )

    def start(self):
        stop_event = threading.Event()
        thread = threading.Thread(target=self.run_forever, kwargs={"stop_event": stop_event}, daemon=True)
        thread.start()
        return DailyOpenStreamHandle(stop_event=stop_event, thread=thread)

    def run_forever(self, *, stop_event) -> None:
        normalized_symbols = tuple(dict.fromkeys(symbol.lower() for symbol in self.symbols if symbol))
        if not normalized_symbols:
            return
        while not stop_event.is_set():
            wait_seconds = _seconds_until_capture_window(self.now_provider())
            if wait_seconds > 0 and stop_event.wait(wait_seconds):
                return
            deadline = _capture_deadline(self.now_provider())
            cycle_stop = threading.Event()
            seen: set[str] = set()

            def _on_message(raw_message) -> None:
                try:
                    payload = json.loads(raw_message) if isinstance(raw_message, (str, bytes)) else raw_message
                except (TypeError, ValueError):
                    return
                update = parse_daily_open_update(payload)
                if update is None:
                    return
                # The subscription starts shortly before UTC midnight so the
                # socket is warm, but only the newly opened day's candle is a
                # daily-open observation for this capture cycle.
                if update.trading_day != deadline.date():
                    return
                self.on_update(update)
                seen.add(update.symbol.lower())
                if len(seen) >= len(normalized_symbols):
                    cycle_stop.set()

            try:
                runner = self.websocket_runner or _default_daily_open_websocket_runner
                runner(
                    url=(
                        BINANCE_TESTNET_FSTREAM_MARKET_WS_URL
                        if self.testnet
                        else BINANCE_FSTREAM_MARKET_WS_URL
                    ),
                    symbols=normalized_symbols,
                    on_message=_on_message,
                    stop_event=stop_event,
                    cycle_stop_event=cycle_stop,
                    deadline=deadline,
                    logger=self.logger,
                )
            except Exception as exc:
                self._log("stream-error", level="WARNING", error=str(exc))
                if stop_event.wait(self.reconnect_delay_seconds):
                    return
                continue
            now = self.now_provider().astimezone(timezone.utc)
            if now < deadline and not stop_event.is_set() and len(seen) < len(normalized_symbols):
                if stop_event.wait(self.reconnect_delay_seconds):
                    return
                continue
            next_window = datetime.combine(now.date(), time(23, 58), tzinfo=timezone.utc)
            if next_window <= now:
                next_window += timedelta(days=1)
            if stop_event.wait(max(0.0, (next_window - now).total_seconds())):
                return


@dataclass
class DailyOpenStreamHandle:
    stop_event: object
    thread: object

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=2)


def _default_daily_open_websocket_runner(
    *,
    url: str,
    symbols: tuple[str, ...],
    on_message,
    stop_event,
    cycle_stop_event,
    deadline: datetime,
    logger=None,
) -> None:
    try:
        import websocket
    except ImportError as exc:
        raise RuntimeError("websocket-client is required for daily open maintenance") from exc

    def _on_open(app) -> None:
        streams = [f"{symbol}@kline_1d" for symbol in symbols]
        for index in range(0, len(streams), 200):
            app.send(
                json.dumps(
                    {
                        "method": "SUBSCRIBE",
                        "params": streams[index : index + 200],
                        "id": index // 200 + 1,
                    }
                )
            )

    app = websocket.WebSocketApp(
        url,
        on_open=_on_open,
        on_message=lambda _app, message: on_message(message),
    )

    def _close_when_done() -> None:
        while not stop_event.is_set() and not cycle_stop_event.is_set():
            if datetime.now(timezone.utc) >= deadline:
                break
            if stop_event.wait(0.25):
                break
        app.close()

    threading.Thread(target=_close_when_done, daemon=True).start()
    app.run_forever(ping_interval=30, ping_timeout=10)
