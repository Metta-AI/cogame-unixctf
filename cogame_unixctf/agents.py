"""Baseline agents and a rollout driver.

These are reference policies, not the trained LLM. They exist to smoke-test the
environment, to bound the reward signal (oracle = ceiling, random = floor), and
to show the shape a real policy plugs into: ``policy(observation) -> command``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from random import Random
from typing import Callable

from .rl_env import UnixCTFEnv

# A policy maps the latest observation to the next shell command.
Policy = Callable[[str], str]


@dataclass
class Rollout:
    score: float
    reward: float
    turns: int
    flags_found: int
    n_flags: int
    transcript: list = field(default_factory=list)  # list[(command, observation)]


def run_rollout(env: UnixCTFEnv, policy: Policy, max_turns: int | None = None) -> Rollout:
    obs = env.reset()
    total_reward = 0.0
    transcript = []
    budget = max_turns if max_turns is not None else env.turn_budget
    for _ in range(budget):
        cmd = policy(obs)
        res = env.step(cmd)
        total_reward += res.reward
        transcript.append((cmd, res.observation))
        obs = res.observation
        if res.done:
            break
    return Rollout(
        score=env.score(),
        reward=total_reward,
        turns=env.turns_used,
        flags_found=res.info["flags_found"],
        n_flags=env.n_flags,
        transcript=transcript,
    )


def oracle_rollout(env: UnixCTFEnv) -> Rollout:
    """Cheating ceiling baseline: replays each flag's ground-truth recovery
    command. Recovers all flags (budget permitting) and is the smoke test that
    every planted flag is recoverable end-to-end inside a real shell session."""
    env.reset()
    assert env.env is not None
    total_reward = 0.0
    transcript = []
    for f in env.env.flags:
        res = env.step(f.oracle_command())
        total_reward += res.reward
        transcript.append((f.oracle_command(), res.observation))
        if res.done:
            break
    return Rollout(
        score=env.score(),
        reward=total_reward,
        turns=env.turns_used,
        flags_found=sum(1 for f in env.env.flags if f.found),
        n_flags=env.n_flags,
        transcript=transcript,
    )


def random_policy(seed: int = 0) -> Policy:
    """Floor baseline: samples generic exploration commands. Occasionally trips a
    flag whose recovery is a bare `cat`, but mostly flails — exactly the
    near-zero early-training signal the eight-flag design is meant to lift."""
    rng = Random(seed)
    menu = [
        "ls -la",
        "find . -type f | head -40",
        "find . -name '*.b64' -o -name '*.gz' -o -name '*.conf' | head",
        "cat etc/hostname",
        "grep -ri flag . 2>/dev/null | head",
        "env",
        "ls -R | head -40",
        "for f in $(find . -type f | head -5); do echo $f; done",
    ]
    return lambda obs: rng.choice(menu)
