from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass

from momentum_alpha.binance_client import BINANCE_FSTREAM_WS_URL, BINANCE_TESTNET_FSTREAM_WS_URL
from momentum_alpha.structured_log import emit_structured_log

from .user_stream_events import parse_user_stream_event

@dataclass
class BinanceUserStreamClient:
    rest_client: object
    testnet: bool = False
    websocket_runner: object | None = None
    keepalive_runner: object | None = None
    stop_event_factory: object | None = None
    logger: Callable[[str], None] | None = None
    keepalive_interval_seconds: int = 30 * 60

    def _log(self, event: str, *, level: str = "INFO", **fields: object) -> None:
        if self.logger is not None:
            emit_structured_log(self.logger, service="user-stream", event=event, level=level, **fields)

    def _parse_raw_message(self, raw_message: str | bytes | dict):
        message_bytes = _raw_message_size(raw_message)
        try:
            if isinstance(raw_message, bytes):
                payload = json.loads(raw_message.decode("utf-8"))
            elif isinstance(raw_message, str):
                payload = json.loads(raw_message)
            else:
                payload = raw_message
        except ValueError as exc:
            self._log("websocket-message-parse-error", level="ERROR", message_bytes=message_bytes, error=str(exc))
            raise

        payload_event_type = payload.get("e") if isinstance(payload, dict) else None
        self._log(
            "websocket-message-raw",
            message_bytes=message_bytes,
            payload_event_type=payload_event_type,
        )
        try:
            return parse_user_stream_event(payload)
        except Exception as exc:
            self._log(
                "websocket-message-parse-error",
                level="ERROR",
                message_bytes=message_bytes,
                payload_event_type=payload_event_type,
                error=str(exc),
            )
            raise

    def build_stream_url(self, *, listen_key: str) -> str:
        base_url = BINANCE_TESTNET_FSTREAM_WS_URL if self.testnet else BINANCE_FSTREAM_WS_URL
        return f"{base_url}/{listen_key}"

    def run_once(self, *, on_event) -> str:
        listen_key = self.rest_client.create_listen_key()["listenKey"]
        if self.websocket_runner is None:
            return listen_key

        def _on_message(raw_message: str | bytes | dict) -> None:
            on_event(self._parse_raw_message(raw_message))

        self.websocket_runner(
            url=self.build_stream_url(listen_key=listen_key),
            on_message=_on_message,
        )
        return listen_key

    def run_forever(self, *, on_event) -> str:
        listen_key = self.rest_client.create_listen_key()["listenKey"]
        stop_event_factory = self.stop_event_factory or threading.Event
        keepalive_stop_event = stop_event_factory()
        keepalive_runner = self.keepalive_runner or _default_keepalive_runner
        keepalive_thread = None
        keepalive_errors: list[BaseException] = []
        if hasattr(self.rest_client, "keepalive_listen_key"):
            def _run_keepalive() -> None:
                try:
                    keepalive_runner(
                        rest_client=self.rest_client,
                        listen_key=listen_key,
                        stop_event=keepalive_stop_event,
                        interval_seconds=self.keepalive_interval_seconds,
                    )
                except BaseException as exc:
                    keepalive_errors.append(exc)
                    keepalive_stop_event.set()
                    if self.logger is not None:
                        emit_structured_log(
                            self.logger,
                            service="user-stream",
                            event="keepalive-error",
                            level="ERROR",
                            error=str(exc),
                        )

            keepalive_thread = threading.Thread(
                target=_run_keepalive,
                daemon=True,
            )
            keepalive_thread.start()

        def _on_message(raw_message: str | bytes | dict) -> None:
            on_event(self._parse_raw_message(raw_message))

        try:
            if self.websocket_runner is None:
                _default_websocket_runner(
                    url=self.build_stream_url(listen_key=listen_key),
                    on_message=_on_message,
                    logger=self.logger,
                    stop_event=keepalive_stop_event,
                )
            else:
                self.websocket_runner(
                    url=self.build_stream_url(listen_key=listen_key),
                    on_message=_on_message,
                )
        finally:
            keepalive_stop_event.set()
            if keepalive_thread is not None:
                keepalive_thread.join(timeout=1)
            close_listen_key = getattr(self.rest_client, "close_listen_key", None)
            if callable(close_listen_key):
                close_listen_key(listen_key=listen_key)
        if keepalive_errors:
            raise keepalive_errors[0]
        return listen_key


def _raw_message_size(raw_message: str | bytes | dict) -> int:
    if isinstance(raw_message, bytes):
        return len(raw_message)
    if isinstance(raw_message, str):
        return len(raw_message.encode("utf-8"))
    return len(json.dumps(raw_message, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _default_websocket_runner(*, url: str, on_message, logger: Callable[[str], None] | None = None, stop_event=None) -> None:
    try:
        import websocket
    except ImportError as exc:
        raise RuntimeError("websocket-client is required to run the Binance user stream") from exc

    def _log(message: str) -> None:
        if logger is not None:
            emit_structured_log(logger, service="user-stream", event=message)

    app = websocket.WebSocketApp(
        url,
        on_message=lambda _app, message: on_message(message),
        on_open=lambda _app: _log("websocket-open"),
        on_error=lambda _app, error: _log(f"websocket-error error={error}"),
        on_close=lambda _app, status, reason: _log(f"websocket-close status={status} reason={reason}"),
    )
    if stop_event is not None:
        def _close_when_stopped() -> None:
            stop_event.wait()
            if stop_event.is_set():
                _log("websocket-stop-requested")
                close = getattr(app, "close", None)
                if callable(close):
                    close()

        threading.Thread(target=_close_when_stopped, daemon=True).start()
    app.run_forever(ping_interval=30, ping_timeout=10)


def _default_keepalive_runner(*, rest_client, listen_key: str, stop_event, interval_seconds: int) -> None:
    while not stop_event.wait(interval_seconds):
        rest_client.keepalive_listen_key(listen_key=listen_key)
