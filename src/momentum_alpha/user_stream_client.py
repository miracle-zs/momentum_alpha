from __future__ import annotations

import json
import threading
from dataclasses import dataclass

from momentum_alpha.binance_client import BINANCE_FSTREAM_WS_URL, BINANCE_TESTNET_FSTREAM_WS_URL

from .user_stream_events import parse_user_stream_event

@dataclass
class BinanceUserStreamClient:
    rest_client: object
    testnet: bool = False
    websocket_runner: object | None = None
    keepalive_runner: object | None = None
    stop_event_factory: object | None = None
    keepalive_interval_seconds: int = 30 * 60

    def build_stream_url(self, *, listen_key: str) -> str:
        base_url = BINANCE_TESTNET_FSTREAM_WS_URL if self.testnet else BINANCE_FSTREAM_WS_URL
        return f"{base_url}/{listen_key}"

    def run_once(self, *, on_event) -> str:
        listen_key = self.rest_client.create_listen_key()["listenKey"]
        if self.websocket_runner is None:
            return listen_key

        def _on_message(raw_message: str | bytes | dict) -> None:
            if isinstance(raw_message, bytes):
                payload = json.loads(raw_message.decode("utf-8"))
            elif isinstance(raw_message, str):
                payload = json.loads(raw_message)
            else:
                payload = raw_message
            on_event(parse_user_stream_event(payload))

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
        if hasattr(self.rest_client, "keepalive_listen_key"):
            keepalive_thread = threading.Thread(
                target=keepalive_runner,
                kwargs={
                    "rest_client": self.rest_client,
                    "listen_key": listen_key,
                    "stop_event": keepalive_stop_event,
                    "interval_seconds": self.keepalive_interval_seconds,
                },
                daemon=True,
            )
            keepalive_thread.start()

        def _on_message(raw_message: str | bytes | dict) -> None:
            if isinstance(raw_message, bytes):
                payload = json.loads(raw_message.decode("utf-8"))
            elif isinstance(raw_message, str):
                payload = json.loads(raw_message)
            else:
                payload = raw_message
            on_event(parse_user_stream_event(payload))

        runner = self.websocket_runner or _default_websocket_runner
        try:
            runner(
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
        return listen_key


def _default_websocket_runner(*, url: str, on_message) -> None:
    try:
        import websocket
    except ImportError as exc:
        raise RuntimeError("websocket-client is required to run the Binance user stream") from exc

    app = websocket.WebSocketApp(url, on_message=lambda _app, message: on_message(message))
    app.run_forever()


def _default_keepalive_runner(*, rest_client, listen_key: str, stop_event, interval_seconds: int) -> None:
    while not stop_event.wait(interval_seconds):
        rest_client.keepalive_listen_key(listen_key=listen_key)
