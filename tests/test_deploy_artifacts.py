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
        self.assertIn('--state-file "${STATE_FILE}"', content)

    def test_install_logrotate_script_installs_project_policy(self) -> None:
        content = (ROOT / "scripts" / "install_logrotate.sh").read_text()
        self.assertIn('deploy/logrotate/momentum-alpha', content)
        self.assertIn('/etc/logrotate.d/momentum-alpha', content)

    def test_install_systemd_script_installs_dashboard_service(self) -> None:
        content = (ROOT / "scripts" / "install_systemd.sh").read_text()
        self.assertIn('deploy/systemd/momentum-alpha-dashboard.service', content)
        self.assertIn('enable --now momentum-alpha-dashboard.service', content)

    def test_logrotate_policy_rotates_project_logs(self) -> None:
        content = (ROOT / "deploy" / "logrotate" / "momentum-alpha").read_text()
        self.assertIn('/var/log/momentum-alpha.log', content)
        self.assertIn('/var/log/momentum-alpha-user-stream.log', content)
        self.assertIn('/var/log/momentum-alpha-dashboard.log', content)
        self.assertIn('daily', content)
        self.assertIn('rotate 14', content)

    def test_dashboard_systemd_unit_executes_dashboard_script(self) -> None:
        content = (ROOT / "deploy" / "systemd" / "momentum-alpha-dashboard.service").read_text()
        self.assertIn('ExecStart=%h/momentum_alpha/scripts/run_dashboard.sh', content)
        self.assertIn('StandardOutput=append:%h/momentum_alpha/var/log/momentum-alpha-dashboard.log', content)
        self.assertIn('StandardError=append:%h/momentum_alpha/var/log/momentum-alpha-dashboard.log', content)

    def test_check_health_script_invokes_healthcheck_command(self) -> None:
        content = (ROOT / "scripts" / "check_health.sh").read_text()
        self.assertIn("healthcheck", content)
        self.assertIn("momentum-alpha.log", content)
        self.assertIn("momentum-alpha-user-stream.log", content)
        self.assertIn("RUNTIME_DB_FILE", content)

    def test_check_health_and_notify_script_invokes_serverchan_helper(self) -> None:
        content = (ROOT / "scripts" / "check_health_and_notify.sh").read_text()
        self.assertIn("check_health.sh", content)
        self.assertIn("-m momentum_alpha.serverchan", content)
        self.assertIn("SERVERCHAN_SENDKEY", content)

    def test_run_dashboard_script_prefers_project_venv_python(self) -> None:
        content = (ROOT / "scripts" / "run_dashboard.sh").read_text()
        self.assertIn('VENV_PYTHON="${PROJECT_ROOT}/.venv/bin/python"', content)
        self.assertIn("dashboard", content)
        self.assertIn("--state-file", content)
        self.assertIn("RUNTIME_DB_FILE", content)

    def test_audit_report_script_invokes_audit_report_command(self) -> None:
        content = (ROOT / "scripts" / "audit_report.sh").read_text()
        self.assertIn("audit-report", content)
        self.assertIn('RUNTIME_DB_FILE', content)

    def test_env_example_contains_serverchan_settings(self) -> None:
        content = (ROOT / "deploy" / "env.example").read_text()
        self.assertIn("SERVERCHAN_SENDKEY=", content)
        self.assertIn("SERVERCHAN_STATUS_FILE=", content)
        self.assertIn("RUNTIME_DB_FILE=", content)

    def test_readme_mentions_dashboard_script(self) -> None:
        content = (ROOT / "README.md").read_text()
        self.assertIn("scripts/run_dashboard.sh", content)
        self.assertIn("dashboard", content)
        self.assertIn("runtime.db", content)
