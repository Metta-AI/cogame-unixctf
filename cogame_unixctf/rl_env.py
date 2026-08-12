"""The RL environment: a gym-style shell loop.

- **Observation**: the text output of the last shell command, plus a short
  status header (turns left, flags found).
- **Action**: a shell command string.
- **Budget**: 18 turns per rollout (the paper's default).
- **Reward**: mechanically verifiable — +1 the first time each of the eight
  tokens appears in command output; the episode ends early once all are found.

This is the interface a GRPO/PPO trainer would sample rollouts from. Training
itself (LoRA, GRPO groups) is out of scope here; see the README.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .environment import DEFAULT_FLAGS, Environment
from .sandbox import Shell

DEFAULT_TURN_BUDGET = 18

SYSTEM_BRIEF = (
    "You are on a {role} host ({hostname}). Somewhere in the filesystem are "
    "{n} hidden flags of the form flag{{...}}. Each is concealed behind one "
    "Unix feature (an encoding, an archive, file metadata, a config, a log, a "
    "database, a certificate, ...). Issue shell commands to recover as many as "
    "you can. You have {turns} commands."
)


@dataclass
class StepResult:
    observation: str
    reward: float
    done: bool
    info: dict = field(default_factory=dict)


class UnixCTFEnv:
    def __init__(
        self,
        seed: int = 0,
        n_flags: int = DEFAULT_FLAGS,
        turn_budget: int = DEFAULT_TURN_BUDGET,
        include_live: bool = False,
        command_timeout: float = 10.0,
    ):
        self.seed = seed
        self.n_flags = n_flags
        self.turn_budget = turn_budget
        self.include_live = include_live
        self.command_timeout = command_timeout
        self.env: Environment | None = None
        self.shell: Shell | None = None
        self.turns_used = 0

    # -- gym-style API -----------------------------------------------------

    def reset(self) -> str:
        self.close()
        self.env = Environment(self.seed, self.n_flags, include_live=self.include_live)
        self.shell = Shell(str(self.env.root), default_timeout=self.command_timeout)
        self.turns_used = 0
        return SYSTEM_BRIEF.format(
            role=self.env.role.name,
            hostname=self.env.hostname,
            n=self.n_flags,
            turns=self.turn_budget,
        )

    def step(self, command: str) -> StepResult:
        if self.env is None or self.shell is None:
            raise RuntimeError("call reset() first")
        if self.turns_used >= self.turn_budget:
            return StepResult("[no turns remaining]", 0.0, True, self._info())

        self.turns_used += 1
        res = self.shell.run(command, timeout=self.command_timeout)
        newly = self.env.credit_output(res.output)
        reward = float(len(newly))

        found = sum(1 for f in self.env.flags if f.found)
        turns_left = self.turn_budget - self.turns_used
        done = found >= self.n_flags or turns_left <= 0 or not self.shell.alive

        header = f"[turn {self.turns_used}/{self.turn_budget} | flags {found}/{self.n_flags}"
        if newly:
            header += " | +" + ",".join(f.technique_id for f in newly)
        header += f" | exit {res.exit_code}]"
        observation = header + "\n" + res.output
        return StepResult(observation, reward, done, self._info(newly))

    def _info(self, newly=None) -> dict:
        assert self.env is not None
        return {
            "turns_used": self.turns_used,
            "flags_found": sum(1 for f in self.env.flags if f.found),
            "n_flags": self.n_flags,
            "newly_found": [f.technique_id for f in (newly or [])],
        }

    def score(self) -> float:
        """Fraction of flags recovered — the paper's per-environment solve signal."""
        assert self.env is not None
        return sum(1 for f in self.env.flags if f.found) / self.n_flags

    def close(self) -> None:
        if self.shell is not None:
            self.shell.close()
            self.shell = None
        if self.env is not None:
            self.env.close()
            self.env = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
