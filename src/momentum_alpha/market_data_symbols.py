from __future__ import annotations

from momentum_alpha.exchange_info import parse_exchange_info


def _resolve_symbols(*, symbols: list[str] | None, client) -> list[str]:
    requested_symbols = [symbol for symbol in (symbols or []) if symbol]
    if requested_symbols:
        return list(dict.fromkeys(requested_symbols))
    return list(parse_exchange_info(client.fetch_exchange_info()).keys())
