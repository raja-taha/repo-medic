from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from repomedic_core.config import get_settings
from repomedic_core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class CommandResult:
    command: str
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def passed(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


class SandboxManager:
    """Resource-limited command execution for untrusted repository code."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def run(
        self,
        workspace: Path,
        command: list[str] | str,
        timeout: int | None = None,
        workdir: str | None = None,
    ) -> CommandResult:
        timeout = timeout or self.settings.sandbox_timeout_seconds
        workspace = Path(workspace).resolve()
        if self.settings.sandbox_enabled and self._docker_available():
            return self._run_docker(workspace, command, timeout, workdir)
        return self._run_local(workspace, command, timeout, workdir)

    def _docker_available(self) -> bool:
        return shutil.which("docker") is not None

    def _run_docker(
        self,
        workspace: Path,
        command: list[str] | str,
        timeout: int,
        workdir: str | None,
    ) -> CommandResult:
        shell_cmd = subprocess.list2cmdline(command) if isinstance(command, list) else command

        docker_cmd = [
            "docker",
            "run",
            "--rm",
            "--memory",
            self.settings.sandbox_memory_limit,
            "--cpus",
            str(self.settings.sandbox_cpu_limit),
            "--workdir",
            f"/workspace/{workdir}" if workdir else "/workspace",
            "-v",
            f"{workspace}:/workspace:rw",
        ]
        if self.settings.sandbox_network_disabled:
            docker_cmd.append("--network=none")
        docker_cmd.extend(
            [
                self.settings.sandbox_image,
                "bash",
                "-lc",
                shell_cmd,
            ]
        )

        logger.info("sandbox_docker_run", command=shell_cmd, workspace=str(workspace))
        try:
            proc = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            # Image missing / daemon issues → degrade to local execution for demos.
            combined = f"{proc.stdout}\n{proc.stderr}".lower()
            if proc.returncode != 0 and (
                "unable to find image" in combined
                or "pull access denied" in combined
                or "cannot connect to the docker daemon" in combined
            ):
                logger.warning("sandbox_docker_fallback_local", reason=proc.stderr[:300])
                return self._run_local(workspace, command, timeout, workdir)
            return CommandResult(
                command=shell_cmd,
                exit_code=proc.returncode,
                stdout=_truncate(proc.stdout),
                stderr=_truncate(proc.stderr),
            )
        except subprocess.TimeoutExpired as exc:
            return CommandResult(
                command=shell_cmd,
                exit_code=124,
                stdout=_truncate(exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")),
                stderr=_truncate(exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "timeout")),
                timed_out=True,
            )

    def _run_local(
        self,
        workspace: Path,
        command: list[str] | str,
        timeout: int,
        workdir: str | None,
    ) -> CommandResult:
        cwd = workspace / workdir if workdir else workspace
        if isinstance(command, str):
            shell = True
            args: str | list[str] = command
            display = command
        else:
            shell = False
            args = command
            display = " ".join(command)

        logger.info("sandbox_local_run", command=display, workspace=str(cwd))
        try:
            proc = subprocess.run(
                args,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=shell,
                check=False,
            )
            return CommandResult(
                command=display,
                exit_code=proc.returncode,
                stdout=_truncate(proc.stdout),
                stderr=_truncate(proc.stderr),
            )
        except subprocess.TimeoutExpired as exc:
            return CommandResult(
                command=display,
                exit_code=124,
                stdout=_truncate(exc.stdout or ""),
                stderr=_truncate(exc.stderr or "timeout"),
                timed_out=True,
            )


def _truncate(text: str | None, limit: int = 50_000) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...[truncated {len(text) - limit} chars]"


def detect_test_command(workspace: Path, language: str) -> list[str]:
    workspace = Path(workspace)
    if language == "python":
        if (workspace / "pytest.ini").exists() or (workspace / "pyproject.toml").exists():
            return ["python", "-m", "pytest", "-q", "--tb=short"]
        if (workspace / "tests").exists() or (workspace / "test").exists():
            return ["python", "-m", "pytest", "-q", "--tb=short"]
        return ["python", "-m", "unittest", "discover", "-q"]
    if language in {"typescript", "javascript"}:
        package_json = workspace / "package.json"
        if package_json.exists():
            return ["npm", "test", "--", "--watchAll=false"]
        return ["npx", "jest", "--ci"]
    return ["echo", "no-test-command"]


def detect_lint_command(workspace: Path, language: str) -> list[str] | None:
    workspace = Path(workspace)
    if language == "python":
        if shutil.which("ruff"):
            return ["ruff", "check", "."]
        return ["python", "-m", "compileall", "-q", "."]
    if language in {"typescript", "javascript"}:
        if (workspace / "package.json").exists():
            return ["npx", "eslint", ".", "--max-warnings=0"]
    return None


def create_temp_workspace(prefix: str = "repomedic-") -> Path:
    return Path(tempfile.mkdtemp(prefix=prefix))