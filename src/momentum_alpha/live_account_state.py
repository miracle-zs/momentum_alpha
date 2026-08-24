from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from momentum_alpha.request_weight_budget import RequestWeightBudget
from momentum_alpha.runtime_sync_state import RuntimeSyncStateStore
from momentum_alpha.strategy_state_codec import StoredStrategyState


ACTIVE_ORDER_STATUSES = {"NEW", "PARTIALLY_FILLED", "PENDING"}
POSITION_MODE_ERROR_MARKERS = (
    "-4061",
    "position side does not match",
    "position mode",
    "positionside",
)
NORMAL_ACCOUNT_REQUEST_WEIGHT_LIMIT = 18


def is_position_mode_error(value: object) -> bool:
    message = str(value or "").lower()
    return any(marker in message for marker in POSITION_MODE_ERROR_MARKERS)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _position_side_from_response(payload: object, *, required: bool) -> str | None:
    dual_side = payload.get("dualSidePosition") if isinstance(payload, dict) else None
    if dual_side in (True, "true", "TRUE", "True"):
        return "LONG"
    if dual_side in (False, "false", "FALSE", "False"):
        return None
    if required:
        raise RuntimeError(f"unable to determine Binance position mode from response={payload!r}")
    return None


def _regular_order_snapshot(order: dict) -> tuple[str, dict] | None:
    order_id = order.get("orderId")
    client_order_id = order.get("clientOrderId") or order.get("origClientOrderId")
    if order_id in (None, ""):
        order_id = (
            f"rest:{order.get('symbol')}:{client_order_id or ''}:"
            f"{order.get('type') or order.get('origType') or ''}:{order.get('stopPrice') or ''}"
        )
    status = str(order.get("status") or "").upper()
    if status and status not in ACTIVE_ORDER_STATUSES:
        return None
    return (
        str(order_id),
        {
            "symbol": order.get("symbol"),
            "status": status or "NEW",
            "execution_type": None,
            "side": order.get("side"),
            "client_order_id": client_order_id,
            "original_order_type": order.get("origType") or order.get("type"),
            "stop_price": order.get("stopPrice"),
            "quantity": order.get("origQty") or order.get("quantity"),
            "event_time": None,
        },
    )


def _algo_order_snapshot(order: dict) -> tuple[str, dict] | None:
    key_id = order.get("clientAlgoId") or order.get("algoId")
    if key_id in (None, ""):
        key_id = (
            f"rest:{order.get('symbol')}:{order.get('orderType') or order.get('type') or ''}:"
            f"{order.get('triggerPrice') or order.get('stopPrice') or ''}"
        )
    status = str(order.get("algoStatus") or order.get("status") or "").upper()
    if status and status not in ACTIVE_ORDER_STATUSES:
        return None
    return (
        f"algo:{key_id}",
        {
            "symbol": order.get("symbol"),
            "status": status or "NEW",
            "side": order.get("side"),
            "client_order_id": order.get("clientAlgoId"),
            "original_order_type": order.get("orderType") or order.get("type"),
            "stop_price": order.get("triggerPrice") or order.get("stopPrice"),
            "quantity": order.get("quantity") or order.get("origQty"),
            "event_time": None,
        },
    )


def _raw_order_from_snapshot(key: str, snapshot: dict) -> dict:
    is_algo = key.startswith("algo:")
    return {
        "symbol": snapshot.get("symbol"),
        "status": snapshot.get("status"),
        "side": snapshot.get("side"),
        "orderId": None if is_algo else key,
        "algoId": key[5:] if is_algo else None,
        "clientOrderId": None if is_algo else snapshot.get("client_order_id"),
        "clientAlgoId": snapshot.get("client_order_id") if is_algo else None,
        "type": snapshot.get("original_order_type"),
        "orderType": snapshot.get("original_order_type"),
        "stopPrice": snapshot.get("stop_price"),
        "triggerPrice": snapshot.get("stop_price"),
        "origQty": snapshot.get("quantity"),
        "quantity": snapshot.get("quantity"),
    }


def _position_risk_from_stored_state(
    stored_state: StoredStrategyState | None,
) -> list[dict]:
    result = []
    for symbol, position in (stored_state.positions or {}).items() if stored_state is not None else ():
        opened_at = max((leg.opened_at for leg in position.legs), default=datetime.now(timezone.utc))
        total_quantity = position.total_quantity
        weighted_entry_price = (
            sum((leg.quantity * leg.entry_price for leg in position.legs), Decimal("0"))
            / total_quantity
            if total_quantity > Decimal("0")
            else Decimal("0")
        )
        result.append(
            {
                "symbol": symbol,
                "positionAmt": str(total_quantity),
                "entryPrice": str(weighted_entry_price),
                "updateTime": int(_utc(opened_at).timestamp() * 1000),
            }
        )
    return result


def _position_risk_from_account_info(
    *,
    account_info: dict | None,
    fallback: list[dict],
    now: datetime,
) -> list[dict]:
    if not isinstance(account_info, dict) or not isinstance(account_info.get("positions"), list):
        return fallback
    fallback_by_symbol = {str(item.get("symbol")): item for item in fallback}
    normalized: list[dict] = []
    for item in account_info["positions"]:
        if not isinstance(item, dict):
            continue
        position_side = str(item.get("positionSide") or "BOTH").upper()
        if position_side not in {"BOTH", "LONG"}:
            continue
        symbol = str(item.get("symbol") or "")
        if not symbol:
            continue
        fallback_item = fallback_by_symbol.get(symbol, {})
        normalized.append(
            {
                **item,
                "symbol": symbol,
                "positionAmt": str(item.get("positionAmt") or "0"),
                "entryPrice": str(item.get("entryPrice") or "0"),
                "updateTime": int(
                    item.get("updateTime")
                    or fallback_item.get("updateTime")
                    or (_utc(now).timestamp() * 1000)
                ),
            }
        )
    return normalized


@dataclass(frozen=True)
class LiveAccountSnapshot:
    position_side: str | None
    account_info: dict | None
    position_risk: tuple[dict, ...]
    open_orders: tuple[dict, ...]
    order_statuses: dict[str, dict]
    request_weight: int
    full_sync: bool


class LiveAccountStateCache:
    """Own account REST synchronization for the lifetime of one poll process."""

    def __init__(
        self,
        *,
        client,
        runtime_db_path: Path | None = None,
        symbol_validation_interval_minutes: int = 5,
    ) -> None:
        self.client = client
        self.runtime_sync_store = (
            RuntimeSyncStateStore(path=runtime_db_path)
            if runtime_db_path is not None
            else None
        )
        self.symbol_validation_interval_minutes = max(1, symbol_validation_interval_minutes)
        self.position_side: str | None = None
        self.position_mode_loaded = False
        self.position_risk: list[dict] = []
        self.order_statuses: dict[str, dict] = {}
        self.last_stored_order_projection: dict[str, dict] | None = None
        self.account_info: dict | None = None
        self.account_info_minute: int | None = None
        self.request_weight_minute: int | None = None
        self.request_weight_used = 0
        self.initialized = False
        self.last_symbol_validation_bucket: int | None = None

    def invalidate_position_mode(self) -> None:
        self.position_mode_loaded = False

    def request_full_sync(self) -> None:
        self.initialized = False

    def _load_position_mode(self, *, budget: RequestWeightBudget, required: bool) -> None:
        if self.position_mode_loaded:
            return
        fetch_position_mode = getattr(self.client, "fetch_position_mode", None)
        if not callable(fetch_position_mode):
            self.position_mode_loaded = True
            self.position_side = None
            return
        budget.spend(30, operation="position-mode")
        try:
            response = fetch_position_mode()
        except Exception as exc:
            if required:
                raise RuntimeError("unable to determine Binance position mode for live submission") from exc
            response = None
        self.position_side = _position_side_from_response(response, required=required)
        self.position_mode_loaded = True

    def _load_account_info(
        self,
        *,
        now: datetime,
        budget: RequestWeightBudget,
        force: bool = False,
    ) -> None:
        minute = int(_utc(now).timestamp() // 60)
        if not force and self.account_info_minute == minute:
            return
        fetch_account_info = getattr(self.client, "fetch_account_info", None)
        self.account_info = None
        if callable(fetch_account_info):
            budget.spend(5, operation="account")
            self.account_info = fetch_account_info()
        self.account_info_minute = minute

    def _replace_symbol_orders(
        self,
        *,
        symbol: str,
        regular_orders: list[dict] | None,
        algo_orders: list[dict] | None,
    ) -> None:
        if regular_orders is not None:
            self.order_statuses = {
                key: value
                for key, value in self.order_statuses.items()
                if key.startswith("algo:") or value.get("symbol") != symbol
            }
            for order in regular_orders:
                snapshot = _regular_order_snapshot(order)
                if snapshot is not None:
                    self.order_statuses[snapshot[0]] = snapshot[1]
        if algo_orders is not None:
            self.order_statuses = {
                key: value
                for key, value in self.order_statuses.items()
                if not key.startswith("algo:") or value.get("symbol") != symbol
            }
            for order in algo_orders:
                snapshot = _algo_order_snapshot(order)
                if snapshot is not None:
                    self.order_statuses[snapshot[0]] = snapshot[1]

    def _full_sync(
        self,
        *,
        now: datetime,
        stored_state: StoredStrategyState | None,
        budget: RequestWeightBudget,
        required_position_mode: bool,
    ) -> None:
        self._load_position_mode(budget=budget, required=required_position_mode)
        self._load_account_info(now=now, budget=budget)
        fetch_position_risk = getattr(self.client, "fetch_position_risk", None)
        if callable(fetch_position_risk):
            budget.spend(5, operation="position-risk-startup")
            self.position_risk = list(fetch_position_risk())
        else:
            self.position_risk = _position_risk_from_stored_state(stored_state)
        # The User Stream worker owns the one unscoped startup/gap sync. Poll
        # starts from that durable projection and validates only held symbols,
        # avoiding a second pair of 40-weight account-wide requests.
        stored_order_projection = {
            str(key): dict(snapshot)
            for key, snapshot in (stored_state.order_statuses or {}).items()
        } if stored_state is not None else {}
        self.order_statuses = stored_order_projection
        self.last_stored_order_projection = {
            key: dict(snapshot)
            for key, snapshot in stored_order_projection.items()
        }
        held_symbols = [
            str(item.get("symbol"))
            for item in self.position_risk
            if Decimal(str(item.get("positionAmt") or "0")) > Decimal("0")
        ]
        self._validate_held_symbols(
            symbols=held_symbols,
            now=now,
            budget=budget,
            force=True,
        )
        self.initialized = True

    def _apply_stored_projection(
        self,
        stored_state: StoredStrategyState | None,
        *,
        include_positions: bool = True,
        include_orders: bool = True,
    ) -> None:
        if stored_state is None:
            return
        if include_orders:
            stored_order_projection = {
                str(key): dict(snapshot)
                for key, snapshot in (stored_state.order_statuses or {}).items()
            }
            if stored_order_projection != self.last_stored_order_projection:
                self.order_statuses = stored_order_projection
                self.last_stored_order_projection = {
                    key: dict(snapshot)
                    for key, snapshot in stored_order_projection.items()
                }
        if include_positions:
            stored_position_risk = _position_risk_from_stored_state(stored_state)
            self.position_risk = stored_position_risk

    def _apply_control_requests(self) -> list:
        if self.runtime_sync_store is None:
            return []
        requests = self.runtime_sync_store.control_requests()
        for request in requests:
            if request.key == "position_mode_refresh":
                self.invalidate_position_mode()
            elif request.key == "account_full_sync":
                self.request_full_sync()
        return requests

    def _clear_control_requests(self, requests: list) -> None:
        if self.runtime_sync_store is None:
            return
        for request in requests:
            if request.key in {"position_mode_refresh", "account_full_sync"}:
                self.runtime_sync_store.clear_control(
                    key=request.key,
                    requested_at=request.requested_at,
                )

    def _validate_held_symbols(
        self,
        *,
        symbols: list[str],
        now: datetime,
        budget: RequestWeightBudget,
        force: bool = False,
    ) -> None:
        bucket = int(_utc(now).timestamp() // (60 * self.symbol_validation_interval_minutes))
        if not force and self.last_symbol_validation_bucket == bucket:
            return
        fetch_open_orders = getattr(self.client, "fetch_open_orders", None)
        fetch_open_algo_orders = getattr(self.client, "fetch_open_algo_orders", None)
        for symbol in sorted(set(symbols)):
            regular_orders = None
            algo_orders = None
            if callable(fetch_open_orders) and budget.can_spend(1):
                budget.spend(1, operation=f"open-orders:{symbol}")
                regular_orders = list(fetch_open_orders(symbol=symbol))
            if callable(fetch_open_algo_orders) and budget.can_spend(1):
                budget.spend(1, operation=f"open-algo-orders:{symbol}")
                algo_orders = list(fetch_open_algo_orders(symbol=symbol))
            if regular_orders is None and algo_orders is None:
                break
            self._replace_symbol_orders(
                symbol=symbol,
                regular_orders=regular_orders,
                algo_orders=algo_orders,
            )
        self.last_symbol_validation_bucket = bucket

    def snapshot(
        self,
        *,
        now: datetime,
        stored_state: StoredStrategyState | None,
        restore_positions: bool,
        submit_orders: bool,
    ) -> LiveAccountSnapshot:
        control_requests = self._apply_control_requests()
        full_sync = not self.initialized
        elevated_sync = full_sync or not self.position_mode_loaded
        # The poll loop also performs one all-market ticker read (weight 2),
        # so keep the normal account slice at 18 to enforce the 20/minute
        # main-loop ceiling end to end.
        budget = RequestWeightBudget(
            limit=150 if elevated_sync else NORMAL_ACCOUNT_REQUEST_WEIGHT_LIMIT
        )
        if full_sync:
            self._full_sync(
                now=now,
                stored_state=stored_state,
                budget=budget,
                required_position_mode=submit_orders,
            )
        else:
            self._load_position_mode(budget=budget, required=submit_orders)
            self._load_account_info(now=now, budget=budget)
        self._apply_stored_projection(
            stored_state,
            include_positions=not full_sync,
            include_orders=not full_sync,
        )
        self.position_risk = _position_risk_from_account_info(
            account_info=self.account_info,
            fallback=self.position_risk,
            now=now,
        )
        if restore_positions and not full_sync:
            held_symbols = [
                str(item.get("symbol"))
                for item in self.position_risk
                if Decimal(str(item.get("positionAmt") or "0")) > Decimal("0")
            ]
            self._validate_held_symbols(symbols=held_symbols, now=now, budget=budget)
        self._clear_control_requests(control_requests)
        return self._build_snapshot(now=now, budget=budget, full_sync=full_sync)

    def refresh_symbols(
        self,
        *,
        symbols: set[str],
        now: datetime,
        stored_state: StoredStrategyState | None,
        refresh_account: bool = False,
    ) -> LiveAccountSnapshot:
        budget = RequestWeightBudget(limit=150)
        self._apply_stored_projection(stored_state)
        if refresh_account:
            self._load_account_info(now=now, budget=budget, force=True)
            self.position_risk = _position_risk_from_account_info(
                account_info=self.account_info,
                fallback=self.position_risk,
                now=now,
            )
        self._validate_held_symbols(
            symbols=sorted(symbols),
            now=now,
            budget=budget,
            force=True,
        )
        return self._build_snapshot(now=now, budget=budget, full_sync=False)

    def _build_snapshot(
        self,
        *,
        now: datetime,
        budget: RequestWeightBudget,
        full_sync: bool,
    ) -> LiveAccountSnapshot:
        minute = int(_utc(now).timestamp() // 60)
        if self.request_weight_minute != minute:
            self.request_weight_minute = minute
            self.request_weight_used = 0
        self.request_weight_used += budget.used
        open_orders = tuple(
            _raw_order_from_snapshot(key, snapshot)
            for key, snapshot in self.order_statuses.items()
            if snapshot.get("status") in ACTIVE_ORDER_STATUSES
        )
        return LiveAccountSnapshot(
            position_side=self.position_side,
            account_info=self.account_info,
            position_risk=tuple(self.position_risk),
            open_orders=open_orders,
            order_statuses=dict(self.order_statuses),
            request_weight=self.request_weight_used,
            full_sync=full_sync,
        )
