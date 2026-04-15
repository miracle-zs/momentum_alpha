from __future__ import annotations

from dataclasses import dataclass

from momentum_alpha.execution import ExecutionPlan


@dataclass
class BinanceBroker:
    client: object

    def submit_execution_plan(self, plan: ExecutionPlan) -> list[dict]:
        responses: list[dict] = []
        for order in plan.entry_orders:
            responses.append(self.client.send(self.client.new_order(**order)))
        for order in plan.stop_orders:
            responses.append(self.client.send(self.client.new_order(**order)))
        return responses

    def replace_stop_orders(self, *, replacements: list[tuple[str, str, str]]) -> list[dict]:
        responses: list[dict] = []
        for symbol, quantity, stop_price in replacements:
            open_orders = self.client.fetch_open_orders(symbol=symbol)
            for order in open_orders:
                if order.get("type") == "STOP_MARKET":
                    self.client.cancel_order(symbol=symbol, order_id=order["orderId"])
            responses.append(
                self.client.send(
                    self.client.new_order(
                        symbol=symbol,
                        side="SELL",
                        type="STOP_MARKET",
                        quantity=quantity,
                        stopPrice=stop_price,
                        workingType="CONTRACT_PRICE",
                    )
                )
            )
        return responses
