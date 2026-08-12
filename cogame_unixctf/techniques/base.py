"""Technique framework: the (plant, recovery) pairs that hide a flag behind a
single Unix feature.

Maps to the paper's "155 canonical techniques across sixteen families". Each
technique is a small, parameterized `plant` function (the analogue of the
paper's ``plant.sh``) that transforms the token so it is *not* present as
plaintext on disk, plus a recovery shell command (``recovery.sh``) that prints
the exact token back.
"""

from __future__ import annotations

import os
import platform as _platform
import shutil
import string
from dataclasses import dataclass, field
from pathlib import Path
from random import Random
from typing import Callable

# The sixteen families from the paper (Section: Task/Challenge Design).
FAMILIES = (
    "config_files",
    "text_processing",
    "encodings",
    "compression",
    "archives",
    "shell_state",
    "fs_metadata",
    "processes_ipc",
    "elf_internals",
    "certificates",
    "logs",
    "system_state",
    "db_formats",
    "media_metadata",
    "account_artifacts",
    "network_artifacts",
)

_SYS = _platform.system()  # "Linux" | "Darwin" | ...


@dataclass
class PlantContext:
    """Everything a plant function needs. One per flag."""

    workdir: Path
    token: str
    rng: Random
    # Live techniques append their background helper Popen objects here; the
    # Environment owns them and terminates them on close.
    procs: list = field(default_factory=list)

    def spawn(self, argv: list[str]):
        import subprocess

        p = subprocess.Popen(
            argv, cwd=str(self.workdir), start_new_session=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        self.procs.append(p)
        return p

    def rand_name(self, prefix: str = "", ext: str = "") -> str:
        body = "".join(self.rng.choice(string.ascii_lowercase + string.digits) for _ in range(8))
        return f"{prefix}{body}{ext}"

    def write(self, relpath: str, data: bytes | str) -> Path:
        p = self.workdir / relpath
        p.parent.mkdir(parents=True, exist_ok=True)
        mode = "wb" if isinstance(data, (bytes, bytearray)) else "w"
        with open(p, mode) as fh:
            fh.write(data)
        return p


@dataclass
class PlantResult:
    """Returned by a plant function: how to get the token back, and what it made."""

    recovery_cmd: str
    artifacts: list[str] = field(default_factory=list)
    note: str = ""


PlantFn = Callable[[PlantContext], PlantResult]


@dataclass
class TechniqueSpec:
    id: str
    family: str
    summary: str
    plant: PlantFn
    tools: tuple[str, ...] = ()
    platforms: tuple[str, ...] = ("Linux", "Darwin")
    # "live" techniques need a running helper process (fifo/socket writers) that
    # must outlive planting. They are excluded from default env sampling and the
    # standard validation pass unless explicitly opted in.
    live: bool = False

    def available(self) -> bool:
        """A technique is usable here only if its platform matches and every
        external tool it needs is on PATH. This is what lets one library run
        portably; unusable techniques are simply skipped, never fabricated."""
        if _SYS not in self.platforms:
            return False
        return all(shutil.which(t) is not None for t in self.tools)

    def unavailable_reason(self) -> str:
        if _SYS not in self.platforms:
            return f"platform {_SYS} not in {self.platforms}"
        missing = [t for t in self.tools if shutil.which(t) is None]
        if missing:
            return f"missing tools: {', '.join(missing)}"
        return ""


REGISTRY: dict[str, TechniqueSpec] = {}


def technique(
    id: str,
    family: str,
    summary: str,
    tools: tuple[str, ...] = (),
    platforms: tuple[str, ...] = ("Linux", "Darwin"),
    live: bool = False,
) -> Callable[[PlantFn], PlantFn]:
    if family not in FAMILIES:
        raise ValueError(f"unknown family {family!r}")

    def deco(fn: PlantFn) -> PlantFn:
        if id in REGISTRY:
            raise ValueError(f"duplicate technique id {id!r}")
        REGISTRY[id] = TechniqueSpec(id, family, summary, fn, tools, platforms, live)
        return fn

    return deco


def all_techniques() -> list[TechniqueSpec]:
    return list(REGISTRY.values())


def available_techniques() -> list[TechniqueSpec]:
    return [t for t in REGISTRY.values() if t.available()]


def current_platform() -> str:
    return _SYS
