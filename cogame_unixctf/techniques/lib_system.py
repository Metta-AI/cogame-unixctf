"""Filesystem-metadata, text-processing, config, log, database, certificate,
account and shell-state families.

These are the techniques that most sharply separate "Unix competence" from
"general programming": the recovery path is a short, idiomatic pipeline, not a
program.
"""

from __future__ import annotations

import base64
import os
import shlex
import sqlite3
import subprocess

from .base import PlantContext, PlantResult, technique

B64 = lambda s: base64.b64encode(s.encode()).decode()  # noqa: E731


# ------------------------------------------------------------ text_processing ---


@technique("txt.interleave", "text_processing", "token interleaved with noise chars", tools=("sed",))
def txt_interleave(ctx: PlantContext) -> PlantResult:
    name = ctx.rand_name("mixed_", ".txt")
    noise = "".join(ctx.rng.choice("QWERTYUIOP") for _ in ctx.token)
    woven = "".join(a + b for a, b in zip(ctx.token, noise))
    ctx.write(name, woven + "\n")
    return PlantResult(rf"sed 's/\(.\)./\1/g' {shlex.quote(name)}", [name])


@technique("txt.column", "text_processing", "token hidden in one column of a table", tools=("awk",))
def txt_column(ctx: PlantContext) -> PlantResult:
    name = ctx.rand_name("table_", ".txt")
    lines = []
    for ch in ctx.token:
        c1 = ctx.rng.randint(100, 999)
        c3 = ctx.rng.choice("abcdefghij")
        lines.append(f"{c1} {ch} {c3}")
    ctx.write(name, "\n".join(lines) + "\n")
    return PlantResult(f"awk '{{print $2}}' {shlex.quote(name)} | tr -d '\\n'", [name])


@technique("txt.grep_marker", "text_processing", "base64 token on a marked line among noise", tools=("grep", "base64"))
def txt_grep_marker(ctx: PlantContext) -> PlantResult:
    name = ctx.rand_name("scratch_", ".txt")
    marker = "XF" + ctx.rand_name()
    lines = [ctx.rand_name("junk ") for _ in range(ctx.rng.randint(4, 9))]
    lines.insert(ctx.rng.randint(0, len(lines)), f"{marker}:{B64(ctx.token)}")
    ctx.write(name, "\n".join(lines) + "\n")
    return PlantResult(
        f"grep {shlex.quote(marker)} {shlex.quote(name)} | cut -d: -f2 | base64 -d", [name]
    )


# ---------------------------------------------------------------- config_files ---


@technique("cfg.ini", "config_files", "base64 token as an ini value", tools=("grep", "base64"))
def cfg_ini(ctx: PlantContext) -> PlantResult:
    name = ctx.rand_name("app_", ".conf")
    body = (
        "[server]\n"
        f"host=10.0.{ctx.rng.randint(0,255)}.{ctx.rng.randint(1,254)}\n"
        f"workers={ctx.rng.randint(2,16)}\n"
        "[secret]\n"
        f"api_token={B64(ctx.token)}\n"
        "verify=true\n"
    )
    ctx.write(name, body)
    return PlantResult(
        f"grep '^api_token=' {shlex.quote(name)} | cut -d= -f2- | base64 -d", [name]
    )


@technique("cfg.json", "config_files", "base64 token nested in a JSON config", tools=("grep", "base64"))
def cfg_json(ctx: PlantContext) -> PlantResult:
    name = ctx.rand_name("settings_", ".json")
    body = (
        "{\n"
        '  "service": "auth",\n'
        f'  "retries": {ctx.rng.randint(1,5)},\n'
        f'  "credential": "{B64(ctx.token)}",\n'
        '  "tls": true\n'
        "}\n"
    )
    ctx.write(name, body)
    return PlantResult(
        f"grep credential {shlex.quote(name)} | grep -oE '[A-Za-z0-9+/=]+' | tail -1 | base64 -d",
        [name],
    )


# ------------------------------------------------------------------------ logs ---


@technique("log.b64line", "logs", "base64 token buried in a noisy service log", tools=("grep", "base64"))
def log_b64line(ctx: PlantContext) -> PlantResult:
    name = ctx.rand_name("service_", ".log")
    lvls = ["INFO", "WARN", "DEBUG"]
    lines = []
    for _ in range(ctx.rng.randint(6, 14)):
        lines.append(f"2026-08-1{ctx.rng.randint(0,9)} {ctx.rng.choice(lvls)} handler ok id={ctx.rng.randint(1000,9999)}")
    tag = "session_token"
    lines.insert(ctx.rng.randint(0, len(lines)), f"2026-08-12 DEBUG auth {tag}={B64(ctx.token)}")
    ctx.write(name, "\n".join(lines) + "\n")
    # sed off the prefix rather than `cut -d=`: base64 padding '=' would truncate at cut.
    return PlantResult(
        f"grep -oE '{tag}=[A-Za-z0-9+/=]+' {shlex.quote(name)} | sed 's/^{tag}=//' | base64 -d", [name]
    )


# ------------------------------------------------------------------ db_formats ---


@technique("db.sqlite", "db_formats", "base64 token in a sqlite row", tools=("sqlite3",))
def db_sqlite(ctx: PlantContext) -> PlantResult:
    name = ctx.rand_name("app_", ".sqlite")
    path = ctx.workdir / name
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE kv(k TEXT, v TEXT)")
    con.executemany(
        "INSERT INTO kv VALUES (?,?)",
        [("version", "3"), ("owner", "svc"), ("secret", B64(ctx.token)), ("ok", "1")],
    )
    con.commit()
    con.close()
    return PlantResult(
        f"sqlite3 {shlex.quote(name)} \"select v from kv where k='secret'\" | base64 -d", [name]
    )


# ---------------------------------------------------------------- certificates ---


@technique("cert.cn", "certificates", "base64 token in an X.509 subject CN", tools=("openssl",))
def cert_cn(ctx: PlantContext) -> PlantResult:
    name = ctx.rand_name("server_", ".pem")
    key = ctx.rand_name("server_", ".key")
    path = ctx.workdir / name
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-keyout", str(ctx.workdir / key), "-out", str(path),
            "-days", "365", "-subj", f"/O=Acme/CN={B64(ctx.token)}",
        ],
        check=True, capture_output=True,
    )
    return PlantResult(
        f"openssl x509 -in {shlex.quote(name)} -noout -subject -nameopt multiline "
        f"| awk '/commonName/{{print $NF}}' | base64 -d",
        [name, key],
    )


# ------------------------------------------------------------- account_artifacts ---


@technique("acct.passwd_gecos", "account_artifacts", "base64 token in a passwd GECOS field", tools=("grep", "base64"))
def acct_passwd(ctx: PlantContext) -> PlantResult:
    name = ctx.rand_name("passwd_")
    user = "svc_" + ctx.rand_name()
    lines = [
        "root:x:0:0:root:/root:/bin/bash",
        "daemon:x:1:1:daemon:/usr/sbin:/usr/sbin/nologin",
        f"{user}:x:997:997:{B64(ctx.token)}:/var/lib/{user}:/usr/sbin/nologin",
        "nobody:x:65534:65534:nobody:/nonexistent:/usr/sbin/nologin",
    ]
    ctx.write(name, "\n".join(lines) + "\n")
    return PlantResult(
        f"grep '^{user}:' {shlex.quote(name)} | cut -d: -f5 | base64 -d", [name]
    )


@technique("acct.netrc", "account_artifacts", "base64 token as a .netrc password", tools=("grep", "base64"))
def acct_netrc(ctx: PlantContext) -> PlantResult:
    name = ctx.rand_name(".netrc_")
    host = ctx.rand_name("host") + ".internal"
    ctx.write(name, f"machine {host}\n  login deploy\n  password {B64(ctx.token)}\n")
    return PlantResult(
        f"grep password {shlex.quote(name)} | awk '{{print $NF}}' | base64 -d", [name]
    )


# --------------------------------------------------------------- network_artifacts ---


@technique("net.http_header", "network_artifacts", "base64 token in a captured HTTP header", tools=("grep", "base64"))
def net_http(ctx: PlantContext) -> PlantResult:
    name = ctx.rand_name("request_", ".http")
    body = (
        "GET /api/v1/status HTTP/1.1\r\n"
        f"Host: {ctx.rand_name('svc')}.internal\r\n"
        "User-Agent: curl/8.4.0\r\n"
        f"X-Auth-Token: {B64(ctx.token)}\r\n"
        "Accept: */*\r\n\r\n"
    )
    ctx.write(name, body)
    return PlantResult(
        f"grep -i '^X-Auth-Token:' {shlex.quote(name)} | awk '{{print $2}}' | tr -d '\\r' | base64 -d",
        [name],
    )


# ------------------------------------------------------------------ shell_state ---


@technique("sh.function", "shell_state", "token returned by a sourced shell function", tools=("bash", "base64"))
def sh_function(ctx: PlantContext) -> PlantResult:
    name = ctx.rand_name("env_", ".sh")
    fn = "get_" + ctx.rand_name()
    ctx.write(name, f"{fn}() {{ printf '%s' '{B64(ctx.token)}' | base64 -d; }}\n")
    return PlantResult(f"bash -c 'source {shlex.quote(name)}; {fn}'", [name])


@technique("sh.envvar", "shell_state", "token as a ROT13 exported env var in a profile", tools=("bash",))
def sh_envvar(ctx: PlantContext) -> PlantResult:
    import codecs

    name = ctx.rand_name("profile_", ".sh")
    var = "SVC_" + ctx.rand_name().upper()
    ctx.write(name, f"export {var}='{codecs.encode(ctx.token, 'rot_13')}'\n")
    return PlantResult(
        f"bash -c 'source {shlex.quote(name)}; printf \"%s\" \"${var}\" | tr \"A-Za-z\" \"N-ZA-Mn-za-m\"'",
        [name],
    )
