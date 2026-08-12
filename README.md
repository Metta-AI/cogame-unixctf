# cogame-unixctf

A self-contained implementation of the mechanics in **"Unix-CTF: Procedural
Environments for Unix Competence Reinforcement Learning"**
([vmax.ai](https://vmax.ai/team/unix-ctf-procedural-environments-for-unix-competence-reinforcement-learning)).

Unix-CTF isolates and trains *Unix competence* — knowing the OS, filesystem,
shell, and file-format conventions — rather than general programming. A shell
agent is dropped into a container dressed as a plausible server, told there are
hidden `flag{…}` tokens, and given a short command budget to recover as many as
it can. Every flag hides its token behind **one** Unix feature; recovering it is
1–5 idiomatic shell commands, not a program.

This package builds those environments, ships a validated technique library,
implements the paper's validation funnel, and exposes a gym-style RL loop.

## Install & try it

```bash
cd cogame-unixctf
python3 -m cogame_unixctf list                    # techniques + availability here
python3 -m cogame_unixctf validate --live         # run the validation funnel
python3 -m cogame_unixctf build --seed 0 --reveal  # build one env, show flags+recoveries
python3 -m cogame_unixctf rollout --agent oracle   # ceiling baseline: recovers 8/8
python3 -m cogame_unixctf rollout --agent random   # floor baseline: ~0/8
python3 -m cogame_unixctf play --seed 0            # play it yourself
python3 -m cogame_unixctf race --seed 1 --verbose  # multi-agent race in one container
```

No dependencies beyond the Python standard library and common Unix tools
(`base64`, `gzip`, `tar`, `openssl`, `sqlite3`, …). Techniques that need a tool
or OS you don't have are detected and skipped, never faked.

## Watch it race

A multi-agent variant runs several agents in **one shared container**, competing to
claim the eight flags — first to surface a token wins it exclusively, so a slower
agent gets sniped a tick later. Three heuristic skill tiers (novice → journeyman →
expert) stand in for the paper's base → GRPO → GRPO+SFT competence gradient (these
are hand-written heuristics, not the trained models).

- **[viz/unixctf-race.html](viz/unixctf-race.html)** — a self-contained, replayable
  esports-style visualizer: a flag board that flips to the claimant's colour, three
  lane terminals typing real commands, a shared 18-tick clock. Hosted copy:
  <https://claude.ai/code/artifact/9f0cd36a-66e6-455e-879e-c6f6e5d2cd47>
- `python3 -m cogame_unixctf race --json run.json` writes the transcript the page replays.
- Details in [viz/README.md](viz/README.md).

## How it maps to the paper

| Paper | Here |
|---|---|
| Container dressed as one of **7 server roles** with realistic noise | [`roles.py`](cogame_unixctf/roles.py) — webserver, database, devbox, CI/CD, mailserver, monitoring, gateway; each lays down dirs, hostname, configs, logs, histories |
| **8 flags per environment** (so 2-of-8 still gives signal) | [`environment.py`](cogame_unixctf/environment.py) — `Environment` plants 8 distinct techniques into scattered subdirs |
| **Techniques across 16 families**, each hiding a token behind one Unix feature | [`techniques/`](cogame_unixctf/techniques/) — 33 techniques across 14 families (see below) |
| Frontier-model exploration → **parameterized `plant.sh`/`recovery.sh`** | each technique is a parameterized `plant(ctx) -> recovery_cmd` (random filenames/paths per build) |
| **Validation funnel**: plaintext-absence, recovery-success, fresh-dir portability, dedup | [`verifier.py`](cogame_unixctf/verifier.py) — exactly these checks; `validate` reports a yield % like the paper's 87.5% |
| **Observation** = shell output; **action** = shell command; **18-turn budget** | [`rl_env.py`](cogame_unixctf/rl_env.py) — `UnixCTFEnv.reset()/step(cmd)`, `turn_budget=18` |
| **Mechanically verifiable reward** (+per flag recovered) | `step()` credits +1 the first time each token appears in output; episode ends when all 8 are found |
| Live container with persistent shell state | [`sandbox.py`](cogame_unixctf/sandbox.py) — one long-lived `bash`; `cd`, exports, and sourced functions persist across turns |

### Families covered

`encodings`, `compression`, `archives`, `config_files`, `text_processing`,
`logs`, `db_formats`, `certificates`, `fs_metadata`, `shell_state`,
`account_artifacts`, `network_artifacts`, `elf_internals`, `processes_ipc`.
Linux-only (`setfattr`/`getfattr` xattrs, `base32`) and tool-gated
(`media_metadata` via `exiftool`) techniques are registered and run wherever
their tools exist. The library is structured so extending toward the paper's 155
canonical techniques is just adding more `@technique` entries.

## The RL interface

```python
from cogame_unixctf.rl_env import UnixCTFEnv

env = UnixCTFEnv(seed=0)          # 8 flags, 18-turn budget
obs = env.reset()                 # system brief: role, hostname, task
while True:
    command = policy(obs)         # your LLM policy: observation -> shell command
    step = env.step(command)
    obs, reward, done = step.observation, step.reward, step.done
    if done:
        break
print(env.score())                # fraction of the 8 flags recovered
```

`policy` is where a trained model plugs in. The paper trains **Qwen3-8B with
GRPO + rank-32 LoRA** (64 trajectories/batch = 8 groups × 8 rollouts, 18 turns
each), reporting base 11.6% → GRPO-from-base 27.6% → GRPO-from-SFT 43.6% solve
rate, with mean episode length dropping 17.2 → 12.7 turns. Two reference
policies are included as signal bounds: `oracle` (replays ground-truth
recoveries — the ceiling and an end-to-end smoke test) and `random` (the
near-zero floor the 8-flag design is meant to lift).

## What this does and does not include

**Included and tested** (47 tests, `python3 -m pytest`): the technique library
and its validation funnel, the dressed 8-flag environment builder, the
persistent-shell sandbox, the gym-style RL env with verifiable reward, and the
baseline policies. Every shipped technique passes plaintext-absence +
fresh-directory recovery.

**Out of scope** (needs infrastructure beyond a single package): the
frontier-model *generation* of new techniques (here they're hand-authored and
validated by the same funnel), the GRPO/LoRA *training loop* (this provides the
environment a trainer samples from, not the trainer), and true container
isolation. Commands run with `cwd` inside a throwaway directory but are **not**
OS-sandboxed — the planted content is benign, but run untrusted policies inside
a real container, as the paper does.

## Layout

```
cogame_unixctf/
  techniques/        # the (plant, recovery) library, one module per family group
    base.py          #   framework: @technique registry, availability gating
    lib_encoding.py  #   encodings / compression / archives
    lib_system.py    #   text / config / logs / db / cert / account / shell / net
    lib_metadata.py  #   fs-metadata / ELF / media / IPC
  roles.py           # 7 server-role dressing profiles
  environment.py     # build a dressed filesystem, plant 8 flags
  sandbox.py         # persistent bash session
  rl_env.py          # gym-style reset/step, 18-turn budget, verifiable reward
  verifier.py        # the validation funnel
  agents.py          # oracle + random baselines, rollout driver
  cli.py             # list / validate / build / rollout / play
tests/               # 47 tests
```
