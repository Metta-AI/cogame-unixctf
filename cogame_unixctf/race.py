"""Multi-agent race: several agents in ONE shared environment instance,
competing to claim the eight flags.

Every agent gets its own persistent shell rooted at the same filesystem and, on
each tick, acts simultaneously from its own last observation. Claims resolve in
agent order, so the first agent to surface a token wins it exclusively — a
slower agent that recovers the same flag one tick later gets sniped and scores
nothing. The clock is shared (18 ticks by default).

The run is captured as a single JSON-able record that a replay front-end can
animate lane-by-lane over a shared timeline.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from .environment import Environment
from .rl_env import SYSTEM_BRIEF
from .sandbox import Shell

DEFAULT_TURN_BUDGET = 18


@dataclass
class AgentSpec:
    name: str
    policy: object  # callable(observation:str) -> command:str  (may be stateful)
    color: str = ""
    priority: int = 0  # same-tick ties resolve highest-priority first


@dataclass
class RaceRecord:
    seed: int
    role: str
    hostname: str
    n_flags: int
    turn_budget: int
    agents: list[dict]
    flags: list[dict]
    tree: list[str]
    ticks: list[dict] = field(default_factory=list)
    winner: str = ""

    def to_dict(self) -> dict:
        return {
            "seed": self.seed,
            "role": self.role,
            "hostname": self.hostname,
            "n_flags": self.n_flags,
            "turn_budget": self.turn_budget,
            "agents": self.agents,
            "flags": self.flags,
            "tree": self.tree,
            "ticks": self.ticks,
            "winner": self.winner,
        }


def _snapshot_tree(root) -> list[str]:
    out = []
    for dirpath, dirs, files in os.walk(root):
        rel = os.path.relpath(dirpath, root)
        rel = "" if rel == "." else rel
        for d in sorted(dirs):
            out.append((rel + "/" + d).lstrip("/") + "/")
        for fn in sorted(files):
            out.append((rel + "/" + fn).lstrip("/"))
    return sorted(out)


class Race:
    def __init__(
        self,
        seed: int,
        agents: list[AgentSpec],
        n_flags: int = 8,
        turn_budget: int = DEFAULT_TURN_BUDGET,
        command_timeout: float = 10.0,
    ):
        self.seed = seed
        self.agents = agents
        self.n_flags = n_flags
        self.turn_budget = turn_budget
        self.command_timeout = command_timeout
        self.env = Environment(seed, n_flags)
        self.shells = [Shell(str(self.env.root), default_timeout=command_timeout) for _ in agents]
        brief = SYSTEM_BRIEF.format(
            role=self.env.role.name, hostname=self.env.hostname, n=n_flags, turns=turn_budget
        )
        self.obs = [brief for _ in agents]

    def run(self) -> RaceRecord:
        rec = RaceRecord(
            seed=self.seed,
            role=self.env.role.name,
            hostname=self.env.hostname,
            n_flags=self.n_flags,
            turn_budget=self.turn_budget,
            agents=[{"name": a.name, "color": a.color, "id": i} for i, a in enumerate(self.agents)],
            flags=[
                {"index": f.index, "technique_id": f.technique_id, "family": f.family, "subdir": f.subdir}
                for f in self.env.flags
            ],
            tree=_snapshot_tree(self.env.root),
        )

        order = sorted(range(len(self.agents)), key=lambda i: (-self.agents[i].priority, i))
        for t in range(1, self.turn_budget + 1):
            # 1) Every agent chooses a command from its own last observation (all
            #    act on the same pre-tick state — a simultaneous round).
            commands = [a.policy(self.obs[i]) for i, a in enumerate(self.agents)]
            # 2) Execute every agent's command.
            results = [self.shells[i].run(commands[i], timeout=self.command_timeout) for i in range(len(self.agents))]
            # 3) Resolve claims by priority: a same-tick tie goes to the more
            #    capable operator. Reaching a flag on an EARLIER tick still wins
            #    outright, so lead changes survive.
            claims = {i: [] for i in range(len(self.agents))}
            for i in order:
                claims[i] = self.env.claim_output(i, results[i].output)

            tick = {"t": t, "moves": []}
            for i in range(len(self.agents)):
                self.obs[i] = self._obs(i, t, commands[i], results[i], claims[i])
                tick["moves"].append(
                    {
                        "agent": i,
                        "cmd": commands[i],
                        "exit": results[i].exit_code,
                        "output": _clip(results[i].output),
                        "claims": [
                            {"index": f.index, "technique_id": f.technique_id, "family": f.family, "token": f.token}
                            for f in claims[i]
                        ],
                        "cwd": self._cwd(i),
                    }
                )
            rec.ticks.append(tick)
            if all(f.claimed_by is not None for f in self.env.flags):
                break

        scores = self._scores()
        rec.agents = [{**a, "score": scores[a["id"]]} for a in rec.agents]
        best = max(rec.agents, key=lambda a: (a["score"], -a["id"]))
        # Only call it a win if someone actually claimed a flag.
        rec.winner = best["name"] if best["score"] > 0 else ""
        return rec

    def _scores(self) -> dict[int, int]:
        s = {i: 0 for i in range(len(self.agents))}
        for f in self.env.flags:
            if f.claimed_by is not None:
                s[f.claimed_by] += 1
        return s

    def _cwd(self, i: int) -> str:
        r = self.shells[i].run("pwd", timeout=2.0)
        if r.timed_out or not r.output.strip():
            return "?"
        # realpath both sides so the macOS /tmp -> /private/var symlink doesn't
        # turn a root-level cwd into a "../../.." path.
        return os.path.relpath(os.path.realpath(r.output.strip()), os.path.realpath(str(self.env.root)))

    def _obs(self, i, t, cmd, res, claimed) -> str:
        got = sum(1 for f in self.env.flags if f.claimed_by == i)
        head = f"[you={self.agents[i].name} tick {t}/{self.turn_budget} yours={got} exit {res.exit_code}]"
        return head + "\n" + res.output

    def close(self):
        for sh in self.shells:
            sh.close()
        self.env.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def _clip(s: str, limit: int = 1600) -> str:
    return s if len(s) <= limit else s[:limit] + f"\n… [+{len(s) - limit} bytes]"
