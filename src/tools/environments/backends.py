"""Terminal execution backends."""

from __future__ import annotations

import asyncio
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class CommandResult:
    stdout: str
    stderr: str
    returncode: int


class TerminalBackend(ABC):
    @abstractmethod
    async def run(self, command: str, *, cwd: str | None = None, timeout: int = 120) -> CommandResult:
        ...


class LocalBackend(TerminalBackend):
    async def run(self, command: str, *, cwd: str | None = None, timeout: int = 120) -> CommandResult:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd or os.getcwd(),
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return CommandResult("", f"Command timed out after {timeout}s", 124)
        return CommandResult(
            stdout=stdout_b.decode("utf-8", errors="replace"),
            stderr=stderr_b.decode("utf-8", errors="replace"),
            returncode=proc.returncode or 0,
        )


class DockerBackend(TerminalBackend):
    def __init__(self, image: str = "python:3.11-slim") -> None:
        self.image = image

    async def run(self, command: str, *, cwd: str | None = None, timeout: int = 120) -> CommandResult:
        workdir = cwd or os.getcwd()
        docker_cmd = (
            f"docker run --rm -v {workdir}:/work -w /work {self.image} sh -c {repr(command)}"
        )
        local = LocalBackend()
        return await local.run(docker_cmd, timeout=timeout + 30)


class SSHBackend(TerminalBackend):
    """Stub SSH backend — returns not configured."""

    async def run(self, command: str, *, cwd: str | None = None, timeout: int = 120) -> CommandResult:
        return CommandResult("", "SSH backend not configured (stub)", 1)


class ModalBackend(TerminalBackend):
    """Stub Modal backend — returns not configured."""

    async def run(self, command: str, *, cwd: str | None = None, timeout: int = 120) -> CommandResult:
        return CommandResult("", "Modal backend not configured (stub)", 1)


def get_backend(name: str, *, docker_image: str = "python:3.11-slim") -> TerminalBackend:
    backends: dict[str, TerminalBackend] = {
        "local": LocalBackend(),
        "docker": DockerBackend(docker_image),
        "ssh": SSHBackend(),
        "modal": ModalBackend(),
    }
    return backends.get(name, LocalBackend())
