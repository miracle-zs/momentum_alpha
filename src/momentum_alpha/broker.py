from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from momentum_alpha.execution import ExecutionPlan
from momentum_alpha.orders import is_strategy_client_order_id

logger = logging.getLogger(__name__)


def _build_replacement_stop_client_order_id(symbol: str, *, now: datetime | None = None) -> str:
    resolved_now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    timestamp_token = resolved_now.strftime("%y%m%d%H%M%S") + f"{resolved_now.microsecond // 1000:03d}"
    symbol_token = "".join(ch for ch in symbol.upper() if ch.isalnum())[-10:] or "UNKNOWN"
    return f"ma_{timestamp_token}_{symbol_token}_r00s"


@dataclass
class BinanceBroker:
    client: object
    last_stop_replacement_failures: list[dict[str, str]] = field(default_factory=list, init=False)

    def submit_execution_plan(self, plan: ExecutionPlan) -> list[dict]:
        responses: list[dict] = []
        submitted_entry_symbols: list[str | None] = []
        for order in plan.entry_orders:
            try:
                responses.append(self.client.send(self.client.new_order(**order)))
                submitted_entry_symbols.append(order.get("symbol"))
            except Exception as exc:
                logger.error(f"entry order failed for {order.get('symbol')}: {exc}")
                submitted_entry_symbols.append(None)
        for index, order in enumerate(plan.stop_orders):
            if index < len(submitted_entry_symbols) and submitted_entry_symbols[index] is None:
                continue
            try:
                responses.append(self.client.send(self.client.new_algo_order(**order)))
            except Exception as exc:
                logger.error(f"stop order failed for {order.get('symbol')}: {exc}")
        return responses

    def replace_stop_orders(self, *, replacements: list[tuple[str, str, str] | tuple[str, str, str, str | None]]) -> list[dict]:
        responses: list[dict] = []
        self.last_stop_replacement_failures = []
        for replacement in replacements:
            if len(replacement) == 3:
                symbol, quantity, stop_price = replacement
                position_side = None
            else:
                symbol, quantity, stop_price, position_side = replacement
            open_orders = self.client.fetch_open_algo_orders(symbol=symbol)
            strategy_stop_orders = []
            for order in open_orders:
                order_type = order.get("type") or order.get("orderType")
                client_algo_id = order.get("clientAlgoId")
                if order_type == "STOP_MARKET" and is_strategy_client_order_id(client_algo_id):
                    strategy_stop_orders.append(order)
            order_params = {
                "symbol": symbol,
                "side": "SELL",
                "type": "STOP_MARKET",
                "quantity": quantity,
                "stopPrice": stop_price,
                "workingType": "CONTRACT_PRICE",
                "newClientOrderId": _build_replacement_stop_client_order_id(symbol),
            }
            if position_side is not None:
                order_params["positionSide"] = position_side
            else:
                order_params["reduceOnly"] = "true"
            try:
                responses.append(
                    self.client.send(self.client.new_algo_order(**order_params))
                )
            except Exception as exc:
                logger.error(f"replacement stop order failed for {symbol}: {exc}")
                self.last_stop_replacement_failures.append(
                    {
                        "symbol": symbol,
                        "quantity": quantity,
                        "stop_price": stop_price,
                        "message": str(exc),
                    }
                )
                continue
            for order in strategy_stop_orders:
                client_algo_id = order.get("clientAlgoId")
                try:
                    self.client.cancel_algo_order(
                        algo_id=order.get("algoId"),
                        client_algo_id=client_algo_id,
                    )
                except Exception as exc:
                    logger.error(f"old stop cancellation failed for {symbol}: {exc}")
        return responses
