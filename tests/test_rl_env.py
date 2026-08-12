from __future__ import annotations

from cogame_unixctf import agents
from cogame_unixctf.flags import is_token, make_token
from cogame_unixctf.rl_env import UnixCTFEnv
from cogame_unixctf.sandbox import Shell


def test_flag_format():
    from random import Random

    t = make_token(Random(0))
    assert is_token(t)
    assert t.startswith("flag{") and t.endswith("}")
    assert not is_token("flag{}")
    assert not is_token("nope")


def test_reset_returns_brief():
    with UnixCTFEnv(seed=0) as env:
        brief = env.reset()
        assert "flag{" in brief.lower() or "flags" in brief.lower()
        assert str(env.turn_budget) in brief


def test_oracle_recovers_all():
    with UnixCTFEnv(seed=0) as env:
        r = agents.oracle_rollout(env)
        assert r.flags_found == r.n_flags == 8
        assert r.score == 1.0
        assert r.reward == 8.0


def test_turn_budget_enforced():
    with UnixCTFEnv(seed=0, turn_budget=3) as env:
        env.reset()
        last = None
        for _ in range(3):
            last = env.step("ls")
        assert last.done  # budget exhausted
        assert env.turns_used == 3


def test_reward_only_on_first_discovery():
    with UnixCTFEnv(seed=1) as env:
        env.reset()
        assert env.env is not None
        cmd = env.env.flags[0].oracle_command()
        r1 = env.step(cmd)
        assert r1.reward == 1.0
        r2 = env.step(cmd)  # same flag again
        assert r2.reward == 0.0


def test_random_floor_scores_low():
    with UnixCTFEnv(seed=0) as env:
        r = agents.run_rollout(env, agents.random_policy(0))
        assert r.score < 0.5  # floor baseline should not solve the env


# -- sandbox behaviour --------------------------------------------------------


def test_shell_cwd_persists(tmp_path):
    (tmp_path / "sub").mkdir()
    sh = Shell(str(tmp_path))
    try:
        sh.run("cd sub")
        res = sh.run("pwd")
        assert res.output.strip().endswith("sub")
    finally:
        sh.close()


def test_shell_env_persists(tmp_path):
    sh = Shell(str(tmp_path))
    try:
        sh.run("export FOO=bar123")
        res = sh.run("echo $FOO")
        assert res.output.strip() == "bar123"
    finally:
        sh.close()


def test_shell_exit_code(tmp_path):
    sh = Shell(str(tmp_path))
    try:
        assert sh.run("true").exit_code == 0
        assert sh.run("false").exit_code == 1
    finally:
        sh.close()


def test_shell_timeout(tmp_path):
    sh = Shell(str(tmp_path), default_timeout=0.5)
    try:
        res = sh.run("sleep 5", timeout=0.5)
        assert res.timed_out
    finally:
        sh.close()
