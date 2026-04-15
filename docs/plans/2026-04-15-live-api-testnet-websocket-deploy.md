# Live API Testnet, User Stream, and Deployment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Binance Testnet support, a minimal user-data WebSocket stream integration layer, and deployment artifacts for running the strategy as a long-lived service.

**Architecture:** Keep the existing polling strategy loop as the execution core, add environment-aware client factories for production vs Testnet, add a thin user-stream module for listen-key lifecycle and event decoding, and add shell/systemd deployment artifacts around the existing CLI. Prefer dependency-light code and injectable boundaries so tests can stay fully local.

**Tech Stack:** Python 3.13, unittest, urllib, shell scripts, systemd unit files

---

### Task 1: Add environment-aware Binance endpoints

**Files:**
- Modify: `src/momentum_alpha/binance_client.py`
- Modify: `src/momentum_alpha/main.py`
- Test: `tests/test_binance_client.py`
- Test: `tests/test_main.py`

**Step 1: Write the failing test**

Add tests for:
- Testnet REST base URL selection
- CLI/client factory propagation of a `testnet` flag

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_binance_client tests.test_main -v`

**Step 3: Write minimal implementation**

Add:
- Testnet base URL constant
- `build_client_from_env()` / `load_runtime_settings_from_env()` style helper
- `--testnet` CLI flag for `run-once-live`, `poll`, and future stream commands

**Step 4: Run tests to verify they pass**

Run targeted tests, then full suite.

**Step 5: Commit**

```bash
git add src/momentum_alpha/binance_client.py src/momentum_alpha/main.py tests/test_binance_client.py tests/test_main.py
git commit -m "feat: add binance testnet configuration"
```

### Task 2: Add listen-key REST lifecycle and user stream module

**Files:**
- Modify: `src/momentum_alpha/binance_client.py`
- Create: `src/momentum_alpha/user_stream.py`
- Modify: `src/momentum_alpha/__init__.py`
- Test: `tests/test_binance_client.py`
- Test: `tests/test_user_stream.py`

**Step 1: Write the failing test**

Add tests for:
- create/keepalive/close listen-key request building
- stream URL selection for prod vs testnet
- event decoding for `ORDER_TRADE_UPDATE` and `ACCOUNT_UPDATE`

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_binance_client tests.test_user_stream -v`

**Step 3: Write minimal implementation**

Add:
- REST methods for listen-key lifecycle
- `BinanceUserStreamClient`
- lightweight event parser and handler callback interface

**Step 4: Run tests to verify they pass**

Run targeted tests, then full suite.

**Step 5: Commit**

```bash
git add src/momentum_alpha/binance_client.py src/momentum_alpha/user_stream.py src/momentum_alpha/__init__.py tests/test_binance_client.py tests/test_user_stream.py
git commit -m "feat: add binance user stream support"
```

### Task 3: Add CLI entrypoint for user stream monitoring

**Files:**
- Modify: `src/momentum_alpha/main.py`
- Test: `tests/test_main.py`

**Step 1: Write the failing test**

Add tests for:
- `user-stream` CLI subcommand
- propagation of `--testnet`
- startup summary output

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_main -v`

**Step 3: Write minimal implementation**

Add:
- `user-stream` subcommand
- client factory reuse
- injectable stream runner for tests

**Step 4: Run tests to verify they pass**

Run targeted tests, then full suite.

**Step 5: Commit**

```bash
git add src/momentum_alpha/main.py tests/test_main.py
git commit -m "feat: add user stream cli entrypoint"
```

### Task 4: Add deployment artifacts and docs

**Files:**
- Create: `scripts/run_poll.sh`
- Create: `deploy/systemd/momentum-alpha.service`
- Create: `deploy/env.example`
- Modify: `README.md`

**Step 1: Write the failing test**

No runtime test needed for static deployment artifacts. Validate via file existence and README references if useful.

**Step 2: Run lightweight verification**

Run: `test -f scripts/run_poll.sh && test -f deploy/systemd/momentum-alpha.service && test -f deploy/env.example`

**Step 3: Write minimal implementation**

Add:
- shell wrapper around `python3 -m momentum_alpha.main poll`
- systemd unit using the wrapper
- env example for prod/testnet and state/log paths
- README deployment section

**Step 4: Run verification**

Run file checks and full unit suite.

**Step 5: Commit**

```bash
git add scripts/run_poll.sh deploy/systemd/momentum-alpha.service deploy/env.example README.md
git commit -m "docs: add deployment artifacts"
```
