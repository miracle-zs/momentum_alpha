from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from dataclasses import replace

from momentum_alpha.binance_client import BINANCE_FSTREAM_WS_URL, BINANCE_TESTNET_FSTREAM_WS_URL
from momentum_alpha.execution import apply_fill
from momentum_alpha.models import Position, PositionLeg, StrategyState
from momentum_alpha.orders import is_strategy_client_order_id


@dataclass(frozen=True)
class UserStreamEvent:
    event_type: str
    payload: dict
    symbol: str | None = None
    order_status: str | None = None
    execution_type: str | None = None
    side: str | None = None
    average_price: Decimal | None = None
    filled_quantity: Decimal | None = None
    last_filled_price: Decimal | None = None
    last_filled_quantity: Decimal | None = None
    realized_pnl: Decimal | None = None
    commission: Decimal | None = None
    commission_asset: str | None = None
    stop_price: Decimal | None = None
    original_order_type: str | None = None
    event_time: datetime | None = None
    order_id: int | None = None
    trade_id: int | None = None
    client_order_id: str | None = None
    # Algo order fields
    algo_id: int | None = None
    client_algo_id: str | None = None
    algo_status: str | None = None
    trigger_price: Decimal | None = None


def parse_user_stream_event(payload: dict) -> UserStreamEvent:
    event_type = payload.get("e", "UNKNOWN")
    order_payload = payload.get("o", {})
    symbol = order_payload.get("s") or payload.get("s")
    event_time_ms = payload.get("T") or payload.get("E") or payload.get("t")

    def _parse_decimal(value):
        try:
            if value in (None, ""):
                return None
            return Decimal(str(value))
        except (InvalidOperation, TypeError):
            return None

    return UserStreamEvent(
        event_type=event_type,
        payload=payload,
        symbol=symbol,
        order_status=order_payload.get("X") or payload.get("X") or payload.get("algoStatus"),
        execution_type=order_payload.get("x"),
        side=order_payload.get("S") or payload.get("S"),
        average_price=_parse_decimal(order_payload.get("ap")),
        filled_quantity=_parse_decimal(order_payload.get("z")),
        last_filled_price=_parse_decimal(order_payload.get("L")),
        last_filled_quantity=_parse_decimal(order_payload.get("l")),
        realized_pnl=_parse_decimal(order_payload.get("rp")),
        commission=_parse_decimal(order_payload.get("n")),
        commission_asset=order_payload.get("N"),
        stop_price=_parse_decimal(order_payload.get("sp")),
        original_order_type=order_payload.get("ot") or payload.get("orderType"),
        event_time=datetime.fromtimestamp(int(event_time_ms) / 1000, tz=timezone.utc) if event_time_ms is not None else None,
        order_id=order_payload.get("i"),
        trade_id=order_payload.get("t"),
        client_order_id=order_payload.get("c"),
        # Algo order fields
        algo_id=payload.get("algoId") or order_payload.get("algoId"),
        client_algo_id=payload.get("clientAlgoId") or order_payload.get("clientAlgoId"),
        algo_status=payload.get("algoStatus") or order_payload.get("algoStatus"),
        trigger_price=_parse_decimal(payload.get("triggerPrice") or order_payload.get("triggerPrice")),
    )


def extract_trade_fill(event: UserStreamEvent) -> dict | None:
    if event.event_type != "ORDER_TRADE_UPDATE":
        return None
    if event.execution_type != "TRADE":
        return None
    if event.symbol is None or event.order_id is None or event.trade_id is None:
        return None
    return {
        "symbol": event.symbol,
        "order_id": str(event.order_id),
        "trade_id": str(event.trade_id),
        "client_order_id": event.client_order_id,
        "order_status": event.order_status,
        "execution_type": event.execution_type,
        "side": event.side,
        "order_type": event.original_order_type,
        "quantity": event.last_filled_quantity,
        "cumulative_quantity": event.filled_quantity,
        "average_price": event.average_price,
        "last_price": event.last_filled_price,
        "realized_pnl": event.realized_pnl,
        "commission": event.commission,
        "commission_asset": event.commission_asset,
    }


def user_stream_event_id(event: UserStreamEvent) -> str | None:
    if event.event_type != "ORDER_TRADE_UPDATE":
        return None
    if event.order_id is None:
        return None
    if event.trade_id is not None:
        return f"{event.event_type}:{event.order_id}:trade:{event.trade_id}"
    event_time = "" if event.event_time is None else event.event_time.isoformat()
    execution_type = "" if event.execution_type is None else event.execution_type
    order_status = "" if event.order_status is None else event.order_status
    return f"{event.event_type}:{event.order_id}:state:{execution_type}:{order_status}:{event_time}"


def extract_order_status_update(event: UserStreamEvent) -> tuple[str, dict | None] | None:
    if event.event_type != "ORDER_TRADE_UPDATE" or event.order_id is None:
        return None
    if (
        event.order_status == "FILLED"
        and event.side == "SELL"
        and event.original_order_type == "STOP_MARKET"
    ):
        return (str(event.order_id), None)
    return (
        str(event.order_id),
        {
            "symbol": event.symbol,
            "status": event.order_status,
            "execution_type": event.execution_type,
            "side": event.side,
            "client_order_id": event.client_order_id,
            "original_order_type": event.original_order_type,
            "stop_price": str(event.stop_price) if event.stop_price is not None else None,
            "event_time": event.event_time.isoformat() if event.event_time is not None else None,
        },
    )


def extract_algo_order_status_update(event: UserStreamEvent) -> tuple[str, dict | None] | None:
    """Extract algo order status from ALGO_UPDATE events for stop-loss tracking."""
    if event.event_type != "ALGO_UPDATE" or event.algo_id is None:
        return None
    # Use "algo:" prefix to distinguish from regular orders
    key = f"algo:{event.algo_id}"
    # Terminal states - remove from tracking
    terminal_statuses = {"TRIGGERED", "CANCELLED", "EXPIRED", "FAILED"}
    if event.algo_status in terminal_statuses:
        return (key, None)
    return (
        key,
        {
            "symbol": event.symbol,
            "status": event.algo_status,
            "side": event.side,
            "client_order_id": event.client_algo_id,
            "original_order_type": "STOP_MARKET",  # Algo orders for this strategy are stop orders
            "stop_price": str(event.trigger_price) if event.trigger_price is not None else None,
            "event_time": event.event_time.isoformat() if event.event_time is not None else None,
        },
    )


def extract_flat_position_symbols(event: UserStreamEvent) -> tuple[str, ...]:
    if event.event_type != "ACCOUNT_UPDATE":
        return ()
    account_payload = event.payload.get("a", {})
    flat_symbols: list[str] = []
    for position_payload in account_payload.get("P", []):
        symbol = position_payload.get("s")
        if symbol in (None, ""):
            continue
        try:
            position_amount = Decimal(str(position_payload.get("pa", "")))
        except (InvalidOperation, TypeError):
            continue
        if position_amount == Decimal("0"):
            flat_symbols.append(symbol)
    return tuple(flat_symbols)


def extract_positive_account_positions(event: UserStreamEvent) -> tuple[tuple[str, Decimal, Decimal], ...]:
    if event.event_type != "ACCOUNT_UPDATE":
        return ()
    account_payload = event.payload.get("a", {})
    positive_positions: list[tuple[str, Decimal, Decimal]] = []
    for position_payload in account_payload.get("P", []):
        symbol = position_payload.get("s")
        if symbol in (None, ""):
            continue
        try:
            position_amount = Decimal(str(position_payload.get("pa", "")))
            entry_price = Decimal(str(position_payload.get("ep", "")))
        except (InvalidOperation, TypeError):
            continue
        if position_amount > Decimal("0"):
            positive_positions.append((symbol, position_amount, entry_price))
    return tuple(positive_positions)


def resolve_stop_price_from_order_statuses(*, symbol: str, order_statuses: dict[str, dict] | None) -> Decimal | None:
    if not order_statuses:
        return None
    # Active statuses include both regular order statuses and algo order statuses
    active_statuses = {"NEW", "PARTIALLY_FILLED", "PENDING"}
    fallback_stop_price: Decimal | None = None
    for order_snapshot in order_statuses.values():
        if order_snapshot.get("symbol") != symbol:
            continue
        if order_snapshot.get("side") != "SELL":
            continue
        if order_snapshot.get("original_order_type") != "STOP_MARKET":
            continue
        if order_snapshot.get("status") not in active_statuses:
            continue
        stop_price = order_snapshot.get("stop_price")
        if stop_price in (None, ""):
            continue
        try:
            parsed = Decimal(str(stop_price))
        except (InvalidOperation, TypeError):
            continue
        if is_strategy_client_order_id(order_snapshot.get("client_order_id")):
            return parsed
        if fallback_stop_price is None:
            fallback_stop_price = parsed
    return fallback_stop_price


def apply_user_stream_event_to_state(
    *,
    state: StrategyState,
    event: UserStreamEvent,
    order_statuses: dict[str, dict] | None = None,
) -> StrategyState:
    if event.event_type == "ACCOUNT_UPDATE":
        flat_symbols = extract_flat_position_symbols(event)
        positions = dict(state.positions)
        for symbol in flat_symbols:
            positions.pop(symbol, None)
        restored_at = event.event_time or datetime.now(timezone.utc)
        for symbol, quantity, entry_price in extract_positive_account_positions(event):
            existing_position = positions.get(symbol)
            resolved_stop_price = resolve_stop_price_from_order_statuses(symbol=symbol, order_statuses=order_statuses)
            stop_price = (
                resolved_stop_price
                if resolved_stop_price is not None
                else (existing_position.stop_price if existing_position is not None else Decimal("0"))
            )
            leg_type = "account_update_synced" if existing_position is not None else "account_update_restored"
            positions[symbol] = Position(
                symbol=symbol,
                stop_price=stop_price,
                legs=(
                    PositionLeg(
                        symbol=symbol,
                        quantity=quantity,
                        entry_price=entry_price,
                        stop_price=stop_price,
                        opened_at=restored_at,
                        leg_type=leg_type,
                    ),
                ),
            )
        if positions == state.positions:
            return state
        return replace(state, positions=positions)

    if event.event_type != "ORDER_TRADE_UPDATE" or event.order_status != "FILLED" or event.symbol is None:
        return state

    if event.side == "BUY" and event.average_price is not None and event.filled_quantity is not None:
        stop_price = event.stop_price if event.stop_price is not None else Decimal("0")
        filled_at = event.event_time or datetime.now(timezone.utc)
        return apply_fill(
            state=state,
            symbol=event.symbol,
            quantity=event.filled_quantity,
            entry_price=event.average_price,
            stop_price=stop_price,
            leg_type="stream_fill",
            filled_at=filled_at,
        )

    if event.side == "SELL" and event.original_order_type == "STOP_MARKET":
        positions = dict(state.positions)
        positions.pop(event.symbol, None)
        return replace(state, positions=positions)

    return state


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
