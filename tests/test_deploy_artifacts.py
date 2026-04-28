import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DeployArtifactTests(unittest.TestCase):
    def test_run_poll_script_prefers_project_venv_python(self) -> None:
        content = (ROOT / "scripts" / "run_poll.sh").read_text()
        self.assertIn('VENV_PYTHON="${PROJECT_ROOT}/.venv/bin/python"', content)
        self.assertIn('exec "${VENV_PYTHON}" -u -m momentum_alpha.main "${ARGS[@]}"', content)
        self.assertIn('RUNTIME_DB_FILE="${RUNTIME_DB_FILE:-${PROJECT_ROOT}/var/runtime.db}"', content)

    def test_run_user_stream_script_prefers_project_venv_python(self) -> None:
        content = (ROOT / "scripts" / "run_user_stream.sh").read_text()
        self.assertIn('VENV_PYTHON="${PROJECT_ROOT}/.venv/bin/python"', content)
        self.assertIn('exec "${VENV_PYTHON}" -u -m momentum_alpha.main "${ARGS[@]}"', content)
        self.assertIn('RUNTIME_DB_FILE="${RUNTIME_DB_FILE:-${PROJECT_ROOT}/var/runtime.db}"', content)
        self.assertIn('--runtime-db-file "${RUNTIME_DB_FILE}"', content)

    def test_install_logrotate_script_installs_project_policy(self) -> None:
        content = (ROOT / "scripts" / "install_logrotate.sh").read_text()
        self.assertIn('deploy/logrotate/momentum-alpha', content)
        self.assertIn('/etc/logrotate.d/momentum-alpha', content)
        self.assertIn('__SERVICE_ROOT__', (ROOT / "deploy" / "logrotate" / "momentum-alpha").read_text())
        self.assertIn('sed "s#__SERVICE_ROOT__#${HOME}/momentum_alpha#g"', content)

    def test_install_systemd_script_installs_dashboard_service(self) -> None:
        content = (ROOT / "scripts" / "install_systemd.sh").read_text()
        self.assertIn('deploy/systemd/momentum-alpha-dashboard.service', content)
        self.assertIn('deploy/systemd/momentum-alpha-rebuild-trade-analytics.service', content)
        self.assertIn('deploy/systemd/momentum-alpha-trade-data-sync.service', content)
        self.assertIn('deploy/systemd/momentum-alpha-trade-data-sync.timer', content)
        self.assertIn('deploy/systemd/momentum-alpha-daily-review-report.service', content)
        self.assertIn('deploy/systemd/momentum-alpha-daily-review-report.timer', content)
        self.assertIn('deploy/systemd/momentum-alpha-user-stream-healthcheck.service', content)
        self.assertIn('deploy/systemd/momentum-alpha-user-stream-healthcheck.timer', content)
        self.assertIn('systemctl start momentum-alpha-rebuild-trade-analytics.service', content)
        self.assertIn('enable --now momentum-alpha-trade-data-sync.timer', content)
        self.assertIn('enable --now momentum-alpha-dashboard.service', content)
        self.assertIn('enable --now momentum-alpha-user-stream.service', content)
        self.assertIn('enable --now momentum-alpha.service', content)
        self.assertIn('enable --now momentum-alpha-daily-review-report.timer', content)
        self.assertIn('enable --now momentum-alpha-user-stream-healthcheck.timer', content)

    def test_logrotate_policy_rotates_project_logs(self) -> None:
        content = (ROOT / "deploy" / "logrotate" / "momentum-alpha").read_text()
        self.assertIn('__SERVICE_ROOT__/var/log/momentum-alpha.log', content)
        self.assertIn('__SERVICE_ROOT__/var/log/momentum-alpha-user-stream.log', content)
        self.assertIn('__SERVICE_ROOT__/var/log/momentum-alpha-user-stream-healthcheck.log', content)
        self.assertIn('__SERVICE_ROOT__/var/log/momentum-alpha-dashboard.log', content)
        self.assertIn('__SERVICE_ROOT__/var/log/momentum-alpha-rebuild-trade-analytics.log', content)
        self.assertIn('__SERVICE_ROOT__/var/log/momentum-alpha-trade-data-sync.log', content)
        self.assertIn('__SERVICE_ROOT__/var/log/momentum-alpha-daily-review-report.log', content)
        self.assertIn('daily', content)
        self.assertIn('rotate 14', content)

    def test_dashboard_systemd_unit_executes_dashboard_script(self) -> None:
        content = (ROOT / "deploy" / "systemd" / "momentum-alpha-dashboard.service").read_text()
        self.assertIn('ExecStart=%h/momentum_alpha/scripts/run_dashboard.sh', content)
        self.assertIn('StandardOutput=append:%h/momentum_alpha/var/log/momentum-alpha-dashboard.log', content)
        self.assertIn('StandardError=append:%h/momentum_alpha/var/log/momentum-alpha-dashboard.log', content)

    def test_rebuild_trade_analytics_unit_executes_rebuild_script(self) -> None:
        content = (ROOT / "deploy" / "systemd" / "momentum-alpha-rebuild-trade-analytics.service").read_text()
        self.assertIn('Type=oneshot', content)
        self.assertIn('ExecStart=%h/momentum_alpha/scripts/run_rebuild_trade_analytics.sh', content)
        self.assertIn(
            'StandardOutput=append:%h/momentum_alpha/var/log/momentum-alpha-rebuild-trade-analytics.log',
            content,
        )
        self.assertIn(
            'StandardError=append:%h/momentum_alpha/var/log/momentum-alpha-rebuild-trade-analytics.log',
            content,
        )

    def test_check_health_script_invokes_healthcheck_command(self) -> None:
        content = (ROOT / "scripts" / "check_health.sh").read_text()
        self.assertIn("healthcheck", content)
        self.assertNotIn("momentum-alpha.log", content)
        self.assertNotIn("momentum-alpha-user-stream.log", content)
        self.assertIn("RUNTIME_DB_FILE", content)

    def test_restart_user_stream_if_unhealthy_restarts_only_on_user_stream_failure(self) -> None:
        content = (ROOT / "scripts" / "restart_user_stream_if_unhealthy.sh").read_text()
        self.assertIn("check_health.sh", content)
        self.assertIn("user_stream_events status=FAIL", content)
        self.assertIn("systemctl restart momentum-alpha-user-stream.service", content)

    def test_user_stream_healthcheck_timer_runs_restart_helper(self) -> None:
        service = (ROOT / "deploy" / "systemd" / "momentum-alpha-user-stream-healthcheck.service").read_text()
        timer = (ROOT / "deploy" / "systemd" / "momentum-alpha-user-stream-healthcheck.timer").read_text()
        self.assertIn("Type=oneshot", service)
        self.assertIn("ExecStart=%h/momentum_alpha/scripts/restart_user_stream_if_unhealthy.sh", service)
        self.assertIn("OnUnitActiveSec=60s", timer)
        self.assertIn("WantedBy=timers.target", timer)

    def test_check_health_and_notify_script_invokes_serverchan_helper(self) -> None:
        content = (ROOT / "scripts" / "check_health_and_notify.sh").read_text()
        self.assertIn("check_health.sh", content)
        self.assertIn("-m momentum_alpha.serverchan", content)
        self.assertIn("SERVERCHAN_SENDKEY", content)
        self.assertIn("--runtime-db-file", content)
        self.assertNotIn("SERVERCHAN_STATUS_FILE", content)

    def test_run_dashboard_script_prefers_project_venv_python(self) -> None:
        content = (ROOT / "scripts" / "run_dashboard.sh").read_text()
        self.assertIn('VENV_PYTHON="${PROJECT_ROOT}/.venv/bin/python"', content)
        self.assertIn("dashboard", content)
        self.assertIn("--runtime-db-file", content)
        self.assertIn("RUNTIME_DB_FILE", content)
        self.assertNotIn("momentum-alpha.log", content)
        self.assertNotIn("momentum-alpha-user-stream.log", content)

    def test_run_rebuild_trade_analytics_script_prefers_project_venv_python(self) -> None:
        content = (ROOT / "scripts" / "run_rebuild_trade_analytics.sh").read_text()
        self.assertIn('VENV_PYTHON="${PROJECT_ROOT}/.venv/bin/python"', content)
        self.assertIn("rebuild-trade-analytics", content)
        self.assertIn("--runtime-db-file", content)
        self.assertIn("RUNTIME_DB_FILE", content)
        self.assertNotIn("momentum-alpha.log", content)
        self.assertNotIn("momentum-alpha-user-stream.log", content)

    def test_run_trade_data_sync_script_backfills_and_rebuilds_analytics(self) -> None:
        content = (ROOT / "scripts" / "run_trade_data_sync.sh").read_text()
        self.assertIn('VENV_PYTHON="${PROJECT_ROOT}/.venv/bin/python"', content)
        self.assertIn('RUNTIME_DB_FILE="${RUNTIME_DB_FILE:-${PROJECT_ROOT}/var/runtime.db}"', content)
        self.assertIn('TRADE_SYNC_LOOKBACK_HOURS="${TRADE_SYNC_LOOKBACK_HOURS:-36}"', content)
        self.assertIn("backfill-binance-trades", content)
        self.assertIn("backfill-account-flows", content)
        self.assertIn("REALIZED_PNL", content)
        self.assertIn("COMMISSION", content)
        self.assertIn("FUNDING_FEE", content)
        self.assertIn("TRANSFER", content)
        self.assertIn("rebuild-trade-analytics", content)

    def test_trade_data_sync_systemd_timer_keeps_review_data_fresh(self) -> None:
        service = (ROOT / "deploy" / "systemd" / "momentum-alpha-trade-data-sync.service").read_text()
        timer = (ROOT / "deploy" / "systemd" / "momentum-alpha-trade-data-sync.timer").read_text()
        self.assertIn("Type=oneshot", service)
        self.assertIn("EnvironmentFile=%h/momentum_alpha/deploy/env.local", service)
        self.assertIn("ExecStart=%h/momentum_alpha/scripts/run_trade_data_sync.sh", service)
        self.assertIn(
            "StandardOutput=append:%h/momentum_alpha/var/log/momentum-alpha-trade-data-sync.log",
            service,
        )
        self.assertIn("OnBootSec=2min", timer)
        self.assertIn("OnUnitActiveSec=15min", timer)
        self.assertIn("Persistent=true", timer)

    def test_audit_report_script_invokes_audit_report_command(self) -> None:
        content = (ROOT / "scripts" / "audit_report.sh").read_text()
        self.assertIn("audit-report", content)
        self.assertIn('RUNTIME_DB_FILE', content)

    def test_daily_review_report_script_invokes_daily_review_report_command(self) -> None:
        content = (ROOT / "scripts" / "run_daily_review_report.sh").read_text()
        self.assertIn("backfill-binance-trades", content)
        self.assertIn("backfill-account-flows", content)
        self.assertIn("REALIZED_PNL", content)
        self.assertIn("COMMISSION", content)
        self.assertIn("FUNDING_FEE", content)
        self.assertIn("TRANSFER", content)
        self.assertIn("BACKFILL_LOOKBACK_HOURS", content)
        self.assertIn("rebuild-trade-analytics", content)
        self.assertIn("daily-review-report", content)
        self.assertIn("--runtime-db-file", content)
        self.assertIn("--stop-budget-usdt", content)

    def test_daily_review_systemd_units_declare_report_schedule(self) -> None:
        service = (ROOT / "deploy" / "systemd" / "momentum-alpha-daily-review-report.service").read_text()
        timer = (ROOT / "deploy" / "systemd" / "momentum-alpha-daily-review-report.timer").read_text()
        self.assertIn("ExecStart=%h/momentum_alpha/scripts/run_daily_review_report.sh", service)
        self.assertIn("daily-review-report", service)
        self.assertIn("OnCalendar=*-*-* 08:30:00", timer)
        self.assertIn("Timezone=Asia/Shanghai", timer)

    def test_env_example_contains_serverchan_settings(self) -> None:
        content = (ROOT / "deploy" / "env.example").read_text()
        self.assertIn("SERVERCHAN_SENDKEY=", content)
        self.assertNotIn("SERVERCHAN_STATUS_FILE=", content)
        self.assertIn("RUNTIME_DB_FILE=", content)

    def test_readme_mentions_dashboard_script(self) -> None:
        content = (ROOT / "README.md").read_text()
        self.assertIn("scripts/run_dashboard.sh", content)
        self.assertIn("dashboard", content)
        self.assertIn("runtime.db", content)
