import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DeployArtifactTests(unittest.TestCase):
    def test_run_poll_script_prefers_project_venv_python(self) -> None:
        content = (ROOT / "scripts" / "run_poll.sh").read_text()
        self.assertIn('VENV_PYTHON="${PROJECT_ROOT}/.venv/bin/python"', content)
        self.assertIn('exec "${VENV_PYTHON}" -m momentum_alpha.main "${ARGS[@]}"', content)

    def test_run_user_stream_script_prefers_project_venv_python(self) -> None:
        content = (ROOT / "scripts" / "run_user_stream.sh").read_text()
        self.assertIn('VENV_PYTHON="${PROJECT_ROOT}/.venv/bin/python"', content)
        self.assertIn('exec "${VENV_PYTHON}" -m momentum_alpha.main "${ARGS[@]}"', content)
