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
            responses.append(self.client.send(self.client.new_algo_order(**order)))
        return responses

    def replace_stop_orders(self, *, replacements: list[tuple[str, str, str] | tuple[str, str, str, str | None]]) -> list[dict]:
        responses: list[dict] = []
        for replacement in replacements:
            if len(replacement) == 3:
                symbol, quantity, stop_price = replacement
                position_side = None
            else:
                symbol, quantity, stop_price, position_side = replacement
            open_orders = self.client.fetch_open_algo_orders(symbol=symbol)
            for order in open_orders:
                if order.get("orderType") == "STOP_MARKET":
                    self.client.cancel_algo_order(
                        algo_id=order.get("algoId"),
                        client_algo_id=order.get("clientAlgoId"),
                    )
            responses.append(
                self.client.send(
                    self.client.new_algo_order(
                        symbol=symbol,
                        side="SELL",
                        type="STOP_MARKET",
                        quantity=quantity,
                        stopPrice=stop_price,
                        workingType="CONTRACT_PRICE",
                        positionSide=position_side,
                    )
                )
            )
        return responses
