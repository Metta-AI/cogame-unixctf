"""Environment builder: a dressed filesystem with eight planted flags.

Maps to the paper's core design decision — plant eight flags per container
rather than one — so that early in training a policy that finds two of eight
still gets signal, instead of the near-all-zero reward of single-flag tasks.
"""

from __future__ import annotations

import shutil
import signal
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from random import Random

from . import roles
from .flags import make_token
from .techniques import PlantContext, TechniqueSpec, available_techniques

DEFAULT_FLAGS = 8


@dataclass
class PlantedFlag:
    index: int
    token: str
    technique_id: str
    family: str
    subdir: str  # relative to root; the flag's plant directory
    recovery_cmd: str  # runs with cwd = root/subdir
    artifacts: list[str] = field(default_factory=list)
    found: bool = False
    claimed_by: int | None = None  # in a race: which agent surfaced it first

    def oracle_command(self) -> str:
        """A single command that prints the token, runnable from anywhere in the
        session. Anchored at the env root ($HOME, set by the sandbox) and wrapped
        in a subshell so it leaves the agent's working directory untouched."""
        return f'(cd "$HOME/{self.subdir}" && {self.recovery_cmd})'


class Environment:
    def __init__(
        self,
        seed: int = 0,
        n_flags: int = DEFAULT_FLAGS,
        include_live: bool = False,
        pool: list[TechniqueSpec] | None = None,
    ):
        self.seed = seed
        self.rng = Random(seed)
        self.n_flags = n_flags
        self.include_live = include_live
        self.root = Path(tempfile.mkdtemp(prefix=f"unixctf_{seed}_"))
        self._procs: list = []
        self.flags: list[PlantedFlag] = []

        pool = pool if pool is not None else available_techniques()
        if not include_live:
            pool = [t for t in pool if not t.live]
        if not pool:
            raise RuntimeError("no techniques available on this host")
        self.pool = pool

        self.role = roles.pick_role(self.rng)
        self.hostname = roles.dress(self.root, self.role, self.rng)
        self._plant_all()

    # -- construction ------------------------------------------------------

    def _choose_techniques(self) -> list[TechniqueSpec]:
        chosen = list(self.pool)
        self.rng.shuffle(chosen)
        if len(chosen) >= self.n_flags:
            return chosen[: self.n_flags]
        # Fewer distinct techniques than flags: top up with repeats.
        while len(chosen) < self.n_flags:
            chosen.append(self.rng.choice(self.pool))
        return chosen

    def _plant_all(self) -> None:
        for i, spec in enumerate(self._choose_techniques()):
            base = self.rng.choice(self.role.dirs)
            subdir = f"{base}/{self.rng.randint(1000,9999)}_{spec.family}"
            (self.root / subdir).mkdir(parents=True, exist_ok=True)
            token = make_token(self.rng)
            ctx = PlantContext(
                workdir=self.root / subdir,
                token=token,
                rng=Random(self.rng.random()),
                procs=self._procs,
            )
            result = spec.plant(ctx)
            self.flags.append(
                PlantedFlag(
                    index=i,
                    token=token,
                    technique_id=spec.id,
                    family=spec.family,
                    subdir=subdir,
                    recovery_cmd=result.recovery_cmd,
                    artifacts=result.artifacts,
                )
            )

    # -- lookups -----------------------------------------------------------

    @property
    def tokens(self) -> set[str]:
        return {f.token for f in self.flags}

    def unfound_tokens(self) -> dict[str, PlantedFlag]:
        return {f.token: f for f in self.flags if not f.found}

    def credit_output(self, output: str) -> list[PlantedFlag]:
        """Mark any not-yet-found flag whose token appears in `output`."""
        newly = []
        for f in self.flags:
            if not f.found and f.token in output:
                f.found = True
                newly.append(f)
        return newly

    def claim_output(self, agent_id: int, output: str) -> list[PlantedFlag]:
        """Race semantics: the first agent to surface a token claims it
        exclusively. A later agent recovering the same flag scores nothing."""
        newly = []
        for f in self.flags:
            if f.claimed_by is None and f.token in output:
                f.claimed_by = agent_id
                f.found = True
                newly.append(f)
        return newly

    # -- lifecycle ---------------------------------------------------------

    def close(self) -> None:
        for p in self._procs:
            try:
                import os

                os.killpg(os.getpgid(p.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError, AttributeError):
                pass
        shutil.rmtree(self.root, ignore_errors=True)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
