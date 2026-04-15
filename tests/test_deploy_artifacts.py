import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DeployArtifactTests(unittest.TestCase):
    def test_run_poll_script_prefers_project_venv_python(self) -> None:
        content = (ROOT / "scripts" / "run_poll.sh").read_text()
        self.assertIn('VENV_PYTHON="${PROJECT_ROOT}/.venv/bin/python"', content)
        self.assertIn('exec "${VENV_PYTHON}" -m momentum_alpha.main "${ARGS[@]}"', content)
        self.assertIn('--audit-log-file "${AUDIT_LOG_FILE}"', content)

    def test_run_user_stream_script_prefers_project_venv_python(self) -> None:
        content = (ROOT / "scripts" / "run_user_stream.sh").read_text()
        self.assertIn('VENV_PYTHON="${PROJECT_ROOT}/.venv/bin/python"', content)
        self.assertIn('exec "${VENV_PYTHON}" -m momentum_alpha.main "${ARGS[@]}"', content)
        self.assertIn('--audit-log-file "${AUDIT_LOG_FILE}"', content)
        self.assertIn('--state-file "${STATE_FILE}"', content)

    def test_install_logrotate_script_installs_project_policy(self) -> None:
        content = (ROOT / "scripts" / "install_logrotate.sh").read_text()
        self.assertIn('deploy/logrotate/momentum-alpha', content)
        self.assertIn('/etc/logrotate.d/momentum-alpha', content)

    def test_logrotate_policy_rotates_project_logs(self) -> None:
        content = (ROOT / "deploy" / "logrotate" / "momentum-alpha").read_text()
        self.assertIn('/var/log/momentum-alpha.log', content)
        self.assertIn('/var/log/momentum-alpha-user-stream.log', content)
        self.assertIn('daily', content)
        self.assertIn('rotate 14', content)

    def test_check_health_script_invokes_healthcheck_command(self) -> None:
        content = (ROOT / "scripts" / "check_health.sh").read_text()
        self.assertIn("healthcheck", content)
        self.assertIn("momentum-alpha.log", content)
        self.assertIn("momentum-alpha-user-stream.log", content)

    def test_audit_report_script_invokes_audit_report_command(self) -> None:
        content = (ROOT / "scripts" / "audit_report.sh").read_text()
        self.assertIn("audit-report", content)
        self.assertIn('AUDIT_LOG_FILE', content)
