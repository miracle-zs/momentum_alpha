from __future__ import annotations

import os

from momentum_alpha.binance_client import BINANCE_TESTNET_FAPI_BASE_URL, BinanceHttpError, BinanceRestClient


def build_rest_client_from_env() -> BinanceRestClient:
    api_key = os.environ["BINANCE_API_KEY"]
    api_secret = os.environ["BINANCE_API_SECRET"]
    use_testnet = os.environ.get("BINANCE_USE_TESTNET", "").strip().lower() in {"1", "true", "yes", "on"}
    kwargs = {"api_key": api_key, "api_secret": api_secret}
    if use_testnet:
        kwargs["base_url"] = BINANCE_TESTNET_FAPI_BASE_URL
    return BinanceRestClient(**kwargs)


def _format_http_error(prefix: str, exc: BinanceHttpError) -> str:
    body = exc.response_body or "<empty>"
    return f"{prefix} status={exc.status_code} body={body}"


def run_private_api_diagnostic(*, client) -> list[str]:
    lines: list[str] = []

    try:
        position_risk = client.fetch_position_risk()
        lines.append(f"position_risk_ok count={len(position_risk)}")
    except BinanceHttpError as exc:
        lines.append(_format_http_error("position_risk_error", exc))
        return lines

    try:
        open_orders = client.fetch_open_orders()
        lines.append(f"open_orders_ok count={len(open_orders)}")
    except BinanceHttpError as exc:
        lines.append(_format_http_error("open_orders_error", exc))
        return lines

    try:
        listen_key_payload = client.create_listen_key()
        listen_key = listen_key_payload.get("listenKey")
        closed = False
        if listen_key:
            client.close_listen_key(listen_key=listen_key)
            closed = True
        lines.append(f"listen_key_ok created={bool(listen_key)} closed={closed}")
    except BinanceHttpError as exc:
        lines.append(_format_http_error("listen_key_error", exc))

    return lines


def cli_main() -> int:
    client = build_rest_client_from_env()
    for line in run_private_api_diagnostic(client=client):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(cli_main())
