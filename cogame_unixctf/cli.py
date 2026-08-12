"""Command-line interface.

    python -m cogame_unixctf list                 # techniques + availability
    python -m cogame_unixctf validate [--live]    # run the validation funnel
    python -m cogame_unixctf build --seed 0       # build one env, show flags
    python -m cogame_unixctf rollout --agent oracle|random --seed 0
    python -m cogame_unixctf play --seed 0        # interactive shell
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter

import json

from . import agents
from .environment import Environment
from .heuristic import HeuristicSolver, make_solver
from .race import AgentSpec, Race
from .rl_env import UnixCTFEnv
from .techniques import all_techniques, available_techniques, current_platform
from .verifier import validate_library

_RACE_COLORS = ["#38bdf8", "#f472b6", "#a3e635", "#fbbf24"]


def cmd_list(args) -> int:
    techs = all_techniques()
    avail = {t.id for t in available_techniques()}
    fam_counts = Counter(t.family for t in techs)
    print(f"platform: {current_platform()}   techniques: {len(techs)}   available here: {len(avail)}\n")
    for t in sorted(techs, key=lambda x: (x.family, x.id)):
        mark = "ok " if t.id in avail else "-- "
        extra = "" if t.id in avail else f"   ({t.unavailable_reason()})"
        live = " [live]" if t.live else ""
        print(f"  {mark}{t.id:<22} {t.family:<18} {t.summary}{live}{extra}")
    print("\nfamilies:", ", ".join(f"{k}={v}" for k, v in sorted(fam_counts.items())))
    return 0


def cmd_validate(args) -> int:
    results = validate_library(include_live=args.live, trials=args.trials)
    ok = [r for r in results if r.ok]
    skipped = [r for r in results if r.skipped]
    failed = [r for r in results if not r.ok and not r.skipped]
    for r in results:
        status = "PASS" if r.ok else ("SKIP" if r.skipped else "FAIL")
        print(f"  [{status}] {r.technique_id:<22} {r.reason}")
    tested = len(results) - len(skipped)
    yield_pct = (100.0 * len(ok) / tested) if tested else 0.0
    print(f"\n{len(ok)}/{tested} passed ({yield_pct:.1f}% yield), {len(skipped)} skipped, {len(failed)} failed")
    return 1 if failed else 0


def cmd_build(args) -> int:
    env = Environment(seed=args.seed, n_flags=args.flags, include_live=args.live)
    try:
        print(f"root: {env.root}")
        print(f"role: {env.role.name}   hostname: {env.hostname}   flags: {len(env.flags)}\n")
        for f in env.flags:
            print(f"  #{f.index}  {f.technique_id:<22} {f.family:<16} {f.subdir}")
            if args.reveal:
                print(f"        token:    {f.token}")
                print(f"        recovery: {f.oracle_command()}")
    finally:
        env.close()
    return 0


def cmd_rollout(args) -> int:
    env = UnixCTFEnv(seed=args.seed, include_live=args.live)
    try:
        if args.agent == "oracle":
            r = agents.oracle_rollout(env)
        else:
            r = agents.run_rollout(env, agents.random_policy(args.seed))
        print(f"agent={args.agent} seed={args.seed}")
        print(f"flags {r.flags_found}/{r.n_flags}   score {r.score:.3f}   reward {r.reward:.0f}   turns {r.turns}")
        if args.verbose:
            for cmd, obs in r.transcript:
                head = obs.splitlines()[0] if obs else ""
                print(f"  $ {cmd}\n    {head}")
    finally:
        env.close()
    return 0


def cmd_race(args) -> int:
    skills = {"novice": 1, "journeyman": 2, "expert": 3}
    names = [n.strip() for n in args.agents.split(",") if n.strip()]
    specs = []
    for i, n in enumerate(names):
        skill = skills.get(n, 2)
        specs.append(
            AgentSpec(
                name=n,
                policy=make_solver(skill, seed=args.seed * 1000 + i),
                color=_RACE_COLORS[i % len(_RACE_COLORS)],
                priority=skill,  # same-tick ties go to the more capable agent
            )
        )
    race = Race(seed=args.seed, agents=specs, turn_budget=args.turns)
    try:
        rec = race.run()
    finally:
        race.close()

    print(f"seed {rec.seed}   {rec.role} host {rec.hostname}   flags {rec.n_flags}   budget {rec.turn_budget}\n")
    for a in rec.agents:
        bar = "#" * a["score"] + "." * (rec.n_flags - a["score"])
        print(f"  {a['name']:<12} [{bar}] {a['score']}/{rec.n_flags}")
    print(f"\nwinner: {rec.winner or '(none)'}   ticks: {len(rec.ticks)}")
    if args.verbose:
        for tick in rec.ticks:
            for m in tick["moves"]:
                if m["claims"]:
                    who = rec.agents[m["agent"]]["name"]
                    fams = ",".join(c["family"] for c in m["claims"])
                    print(f"  tick {tick['t']:>2}  {who:<12} claims {fams}")
    if args.json:
        with open(args.json, "w") as fh:
            json.dump(rec.to_dict(), fh, indent=2)
        print(f"\nwrote {args.json}")
    return 0


def cmd_play(args) -> int:
    env = UnixCTFEnv(seed=args.seed, include_live=args.live)
    brief = env.reset()
    print(brief)
    print("(type shell commands; 'quit' to exit)\n")
    try:
        while True:
            try:
                cmd = input("$ ")
            except (EOFError, KeyboardInterrupt):
                break
            if cmd.strip() in ("quit", "exit"):
                break
            res = env.step(cmd)
            print(res.observation)
            if res.done:
                print(f"\n[done] score {env.score():.3f}")
                break
    finally:
        env.close()
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="cogame_unixctf", description="Procedural Unix CTF for RL")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("list", help="list techniques and availability")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("validate", help="run the validation funnel over the library")
    sp.add_argument("--live", action="store_true", help="include live (process/IPC) techniques")
    sp.add_argument("--trials", type=int, default=2)
    sp.set_defaults(func=cmd_validate)

    sp = sub.add_parser("build", help="build one environment and describe its flags")
    sp.add_argument("--seed", type=int, default=0)
    sp.add_argument("--flags", type=int, default=8)
    sp.add_argument("--live", action="store_true")
    sp.add_argument("--reveal", action="store_true", help="print tokens and recovery commands")
    sp.set_defaults(func=cmd_build)

    sp = sub.add_parser("rollout", help="run a baseline agent for one episode")
    sp.add_argument("--agent", choices=["oracle", "random"], default="oracle")
    sp.add_argument("--seed", type=int, default=0)
    sp.add_argument("--live", action="store_true")
    sp.add_argument("--verbose", action="store_true")
    sp.set_defaults(func=cmd_rollout)

    sp = sub.add_parser("race", help="run several agents in one shared environment, racing to claim flags")
    sp.add_argument("--seed", type=int, default=0)
    sp.add_argument("--agents", default="novice,journeyman,expert", help="comma-separated skill tiers")
    sp.add_argument("--turns", type=int, default=18)
    sp.add_argument("--verbose", action="store_true", help="print each claim as it happens")
    sp.add_argument("--json", help="write the race transcript to this path")
    sp.set_defaults(func=cmd_race)

    sp = sub.add_parser("play", help="interactive shell session against one environment")
    sp.add_argument("--seed", type=int, default=0)
    sp.add_argument("--live", action="store_true")
    sp.set_defaults(func=cmd_play)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
