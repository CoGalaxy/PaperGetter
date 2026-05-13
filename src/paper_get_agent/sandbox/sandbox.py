"""代码沙箱.

在隔离环境中执行 LLM 生成的验证代码.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


class CodeSandbox:
    """代码执行沙箱.

    优先用 Docker，不可用时回退到 subprocess.
    """

    def __init__(
        self,
        *,
        engine: str = "docker",
        timeout: int = 60,
        memory_limit: str = "512m",
    ) -> None:
        self.engine = engine
        self.timeout = timeout
        self.memory_limit = memory_limit

    def run(self, code: str) -> str:
        """执行代码并返回 stdout + stderr."""
        if self.engine == "docker":
            return self._run_docker(code)
        return self._run_subprocess(code)

    def _run_docker(self, code: str) -> str:
        """在 Docker 容器中执行."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", encoding="utf-8", delete=False
        ) as f:
            f.write(code)
            script_path = f.name

        try:
            result = subprocess.run(
                [
                    "docker", "run", "--rm",
                    "--memory", self.memory_limit,
                    "--network", "none",
                    "--cpus", "1",
                    "-v", f"{script_path}:/code/main.py:ro",
                    "python:3.11-slim",
                    "timeout", str(self.timeout),
                    "python", "/code/main.py",
                ],
                capture_output=True, text=True, timeout=self.timeout + 10,
            )
            return self._combine_output(result.stdout, result.stderr)
        except subprocess.TimeoutExpired:
            return "[SANDBOX] 代码执行超时"
        except FileNotFoundError:
            # Docker 不可用
            return self._run_subprocess(code)
        finally:
            Path(script_path).unlink(missing_ok=True)

    def _run_subprocess(self, code: str) -> str:
        """子进程执行（Docker 不可用时的回退）."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", encoding="utf-8", delete=False
        ) as f:
            f.write(code)
            script_path = f.name

        try:
            result = subprocess.run(
                ["python", script_path],
                capture_output=True, text=True, timeout=self.timeout,
            )
            return self._combine_output(result.stdout, result.stderr)
        except subprocess.TimeoutExpired:
            return "[SANDBOX] 代码执行超时"
        except Exception as e:
            return f"[SANDBOX] 执行出错: {e}"
        finally:
            Path(script_path).unlink(missing_ok=True)

    @staticmethod
    def _combine_output(stdout: str, stderr: str) -> str:
        parts: list[str] = []
        if stdout.strip():
            parts.append(stdout.strip())
        if stderr.strip():
            parts.append(f"[STDERR]\n{stderr.strip()}")
        return "\n\n".join(parts) if parts else "[SANDBOX] 无输出"
