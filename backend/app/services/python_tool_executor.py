"""
Execute user-defined Python tool code in an isolated sandbox.

User tool code is untrusted. Two execution backends are available, selected by
the ``HEYM_PYTHON_TOOL_SANDBOX`` environment variable:

* ``docker`` - run the tool inside a throwaway, hardened container: no network,
  read-only root filesystem, non-root user, all Linux capabilities dropped,
  ``no-new-privileges``, strict CPU / memory / PID limits, and crucially **no**
  Docker socket. This is the real security boundary and the recommended mode for
  any multi-user / production deployment.
* ``subprocess`` - run the tool in a local Python subprocess with a scrubbed
  environment. This relies only on the in-process allowlist / AST checks in
  ``python_tool_runner``, which are **best effort and NOT a security boundary**
  (in-process Python sandboxes are escapable). It must be selected explicitly
  and is intended only for trusted code or local development.
* ``auto`` (default) - require a Docker sandbox. If Docker is unavailable the
  call **fails closed** (raises) instead of silently running untrusted code
  without OS isolation; select ``subprocess`` to opt into the insecure fallback.

The user code is never bind-mounted or written to a shared location: the JSON
payload (including the code) is streamed to the runner over stdin and the result
is read from stdout. The runner module (``python_tool_runner.py``) is baked into
the backend image, so the Docker backend just invokes it inside a sibling
container of the same image.
"""

import json
import logging
import os
import socket
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

_RUNNER_FILENAME = "python_tool_runner.py"
# Path of the runner module inside the backend image (Dockerfile: COPY backend/ .
# with WORKDIR /app -> backend/app/services/python_tool_runner.py = /app/...).
_DEFAULT_CONTAINER_RUNNER_PATH = "/app/app/services/python_tool_runner.py"

_docker_available_cache: bool | None = None


def _sandbox_mode() -> str:
    raw = os.environ.get("HEYM_PYTHON_TOOL_SANDBOX", "auto").strip().lower()
    if raw not in ("auto", "docker", "subprocess"):
        logger.warning("Unknown HEYM_PYTHON_TOOL_SANDBOX=%r; defaulting to 'auto'", raw)
        return "auto"
    return raw


def _docker_available() -> bool:
    """Return True when a working Docker daemon is reachable (cached)."""
    global _docker_available_cache
    if _docker_available_cache is not None:
        return _docker_available_cache
    try:
        result = subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        _docker_available_cache = result.returncode == 0 and bool(result.stdout.strip())
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        _docker_available_cache = False
    return _docker_available_cache


def _resolve_image() -> str | None:
    """Resolve the image to run tools in: explicit override, else this container's image."""
    override = os.environ.get("HEYM_PYTHON_TOOL_IMAGE", "").strip()
    if override:
        return override
    try:
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.Config.Image}}", socket.gethostname()],
            capture_output=True,
            text=True,
            timeout=5,
        )
        image = result.stdout.strip()
        if result.returncode == 0 and image:
            return image
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        pass
    return None


def _runner_local_path() -> str:
    return str(Path(__file__).resolve().parent / _RUNNER_FILENAME)


def _parse_runner_output(stdout: str | None) -> object:
    try:
        out = json.loads((stdout or "").strip())
    except (json.JSONDecodeError, AttributeError) as e:
        raise ValueError(f"Tool output invalid: {(stdout or '')[:200]}") from e
    if not out.get("success") and "error" in out:
        raise ValueError(f"Tool error: {out['error']}")
    return out.get("result")


def _execute_subprocess(payload_json: str, timeout_seconds: float) -> str:
    """Run the tool runner in a local subprocess with a scrubbed environment."""
    safe_env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONIOENCODING": "utf-8",
        "PYTHONSAFEPATH": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    with tempfile.TemporaryDirectory() as execution_cwd:
        proc = subprocess.Popen(
            [sys.executable, _runner_local_path()],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=execution_cwd,
            env=safe_env,
        )
        try:
            stdout, stderr = proc.communicate(input=payload_json, timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            raise TimeoutError(f"Tool execution timed out after {timeout_seconds} seconds")
    if stderr:
        logger.warning("Tool stderr: %s", stderr)
    return stdout


def _force_remove_container(name: str) -> None:
    try:
        subprocess.run(
            ["docker", "rm", "-f", name],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        pass


def _build_docker_command(image: str, name: str) -> list[str]:
    """Build a hardened, throwaway `docker run` invocation for the tool runner."""
    runner_path = os.environ.get("HEYM_PYTHON_TOOL_RUNNER_PATH", _DEFAULT_CONTAINER_RUNNER_PATH)
    memory = os.environ.get("HEYM_PYTHON_TOOL_MEMORY", "256m")
    return [
        "docker",
        "run",
        "--rm",
        "-i",
        "--name",
        name,
        "--network",
        os.environ.get("HEYM_PYTHON_TOOL_NETWORK", "none"),
        "--read-only",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=64m",
        "--workdir",
        "/tmp",
        "--user",
        os.environ.get("HEYM_PYTHON_TOOL_USER", "65534:65534"),
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        os.environ.get("HEYM_PYTHON_TOOL_PIDS", "128"),
        "--memory",
        memory,
        "--memory-swap",
        memory,
        "--cpus",
        os.environ.get("HEYM_PYTHON_TOOL_CPUS", "1"),
        # Override the backend image ENTRYPOINT (entrypoint.sh starts uvicorn and
        # ignores its args) so the container actually runs the tool runner.
        "--entrypoint",
        "python",
        "--env",
        "PYTHONDONTWRITEBYTECODE=1",
        "--env",
        "PYTHONIOENCODING=utf-8",
        image,
        runner_path,
    ]


def _execute_docker(payload_json: str, timeout_seconds: float, image: str) -> str:
    """Run the tool runner inside a hardened, throwaway sibling container."""
    name = f"heym-pytool-{uuid.uuid4().hex}"
    cmd = _build_docker_command(image, name)
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        stdout, stderr = proc.communicate(input=payload_json, timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        _force_remove_container(name)
        raise TimeoutError(f"Tool execution timed out after {timeout_seconds} seconds")
    if stderr:
        logger.warning("Docker tool stderr: %s", stderr)
    return stdout


def execute_tool(
    code: str,
    function_name: str,
    arguments: dict,
    timeout_seconds: float = 30.0,
) -> object:
    """
    Execute user Python tool code in an isolated sandbox with a timeout.

    Args:
        code: Python function code (e.g. "def count_characters(text: str): return len(text)")
        function_name: Name of the function to call
        arguments: Dict of keyword arguments to pass to the function
        timeout_seconds: Max execution time in seconds

    Returns:
        The return value of the function (must be JSON-serializable).

    Raises:
        TimeoutError: If execution exceeds timeout_seconds
        ValueError: If tool validation fails or the tool returns an error
        RuntimeError: If the configured sandbox backend is unavailable
    """
    payload_json = json.dumps(
        {"code": code, "function_name": function_name, "arguments": arguments},
        default=str,
    )

    mode = _sandbox_mode()

    if mode == "subprocess":
        logger.warning(
            "HEYM_PYTHON_TOOL_SANDBOX=subprocess: executing the tool in a local subprocess. "
            "This is NOT a security boundary and must only be used for trusted code or local "
            "development."
        )
        return _parse_runner_output(_execute_subprocess(payload_json, timeout_seconds))

    # mode == "auto" or "docker": require a real Docker sandbox and fail closed
    # rather than silently running untrusted code without OS isolation.
    if not _docker_available():
        raise RuntimeError(
            "Python tool execution requires a Docker sandbox but no working Docker daemon is "
            "reachable. Run with Docker available, or set HEYM_PYTHON_TOOL_SANDBOX=subprocess to "
            "explicitly allow the insecure local fallback (trusted/dev use only)."
        )
    image = _resolve_image()
    if image is None:
        raise RuntimeError(
            "Python tool Docker sandbox is enabled but the runner image could not be resolved. "
            "Set HEYM_PYTHON_TOOL_IMAGE to the backend image."
        )
    return _parse_runner_output(_execute_docker(payload_json, timeout_seconds, image))
