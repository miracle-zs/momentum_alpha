from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def _load_status(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    status = payload.get("status")
    return str(status) if status in {"OK", "FAIL"} else None


def _save_status(*, path: Path, status: str, now: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "status": status,
                "updated_at": now.astimezone(timezone.utc).isoformat(),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _current_status(health_output: str) -> str:
    for line in health_output.splitlines():
        if line.startswith("overall="):
            return line.split("=", 1)[1].strip()
    raise ValueError("health output missing overall= line")


def _notification_event(*, previous_status: str | None, current_status: str) -> str:
    if current_status == "FAIL" and previous_status != "FAIL":
        return "fail"
    if current_status == "OK" and previous_status == "FAIL":
        return "recovered"
    return "none"


def _build_message(*, event: str, hostname: str, health_output: str) -> tuple[str, str]:
    if event == "fail":
        title = f"Momentum Alpha 健康告警 @ {hostname}"
    elif event == "recovered":
        title = f"Momentum Alpha 已恢复 @ {hostname}"
    else:
        raise ValueError(f"unsupported event: {event}")
    body = f"主机: {hostname}\n\n{health_output.strip()}\n"
    return title, body


def _send_notification(
    *,
    sendkey: str,
    title: str,
    body: str,
    opener=urlopen,
) -> None:
    payload = urlencode({"text": title, "desp": body}).encode("utf-8")
    request = Request(
        url=f"https://sctapi.ftqq.com/{sendkey}.send",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with opener(request, timeout=10) as response:
        response.read()


def process_health_notification(
    *,
    sendkey: str,
    status_file: Path,
    health_output: str,
    now: datetime,
    hostname: str,
    opener=urlopen,
) -> dict:
    previous_status = _load_status(status_file)
    current_status = _current_status(health_output)
    event = _notification_event(previous_status=previous_status, current_status=current_status)
    notified = False
    if event != "none":
        title, body = _build_message(event=event, hostname=hostname, health_output=health_output)
        _send_notification(sendkey=sendkey, title=title, body=body, opener=opener)
        notified = True
    _save_status(path=status_file, status=current_status, now=now)
    return {
        "previous_status": previous_status,
        "current_status": current_status,
        "event": event,
        "notified": notified,
    }


def cli_main(
    *,
    argv: list[str] | None = None,
    now_provider: Callable[[], datetime] | None = None,
    opener=urlopen,
    stdout=None,
) -> int:
    parser = argparse.ArgumentParser(prog="momentum_alpha.serverchan")
    parser.add_argument("--sendkey", required=True)
    parser.add_argument("--status-file", required=True)
    parser.add_argument("--health-output-file")
    parser.add_argument("--hostname", default=os.uname().nodename)
    args = parser.parse_args(argv)

    if args.health_output_file:
        health_output = Path(args.health_output_file).read_text(encoding="utf-8")
    else:
        health_output = input()
    now_provider = now_provider or (lambda: datetime.now(timezone.utc))
    stdout = stdout or __import__("sys").stdout
    result = process_health_notification(
        sendkey=args.sendkey,
        status_file=Path(os.path.abspath(args.status_file)),
        health_output=health_output,
        now=now_provider(),
        hostname=args.hostname,
        opener=opener,
    )
    stdout.write(
        f"status={result['current_status']} previous={result['previous_status']} "
        f"event={result['event']} notified={'yes' if result['notified'] else 'no'}\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(cli_main())
