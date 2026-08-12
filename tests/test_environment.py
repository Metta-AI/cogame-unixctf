from __future__ import annotations

import os

from cogame_unixctf.environment import Environment


def test_builds_eight_flags():
    with Environment(seed=0) as env:
        assert len(env.flags) == 8
        assert env.role.name
        assert env.hostname


def test_tokens_absent_as_plaintext_across_whole_env():
    """No planted token may appear as plaintext anywhere in the dressed
    filesystem — otherwise `grep -r flag` would trivialise the environment."""
    with Environment(seed=3) as env:
        tokens = [f.token.encode() for f in env.flags]
        for dirpath, _dirs, files in os.walk(env.root):
            for fn in files:
                p = os.path.join(dirpath, fn)
                if os.path.islink(p) or not os.path.isfile(p):
                    continue
                try:
                    with open(p, "rb") as fh:
                        data = fh.read()
                except OSError:
                    continue
                for tok in tokens:
                    assert tok not in data, f"{tok!r} leaked into {p}"


def test_determinism_same_seed():
    a = Environment(seed=7)
    b = Environment(seed=7)
    try:
        assert [f.technique_id for f in a.flags] == [f.technique_id for f in b.flags]
        assert a.role.name == b.role.name
        # Tokens are random per build even at the same seed structure? No — same
        # seed reproduces the full build including tokens.
        assert [f.token for f in a.flags] == [f.token for f in b.flags]
    finally:
        a.close()
        b.close()


def test_credit_output_marks_found():
    with Environment(seed=1) as env:
        tok = env.flags[0].token
        newly = env.credit_output(f"here is the {tok} yay")
        assert [f.index for f in newly] == [0]
        assert env.flags[0].found
        # Idempotent: crediting again yields nothing new.
        assert env.credit_output(tok) == []


def test_cleanup_removes_root():
    env = Environment(seed=2)
    root = env.root
    assert root.exists()
    env.close()
    assert not root.exists()
