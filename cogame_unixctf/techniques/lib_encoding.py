"""Encoding / compression / archive families.

The planted content is produced deterministically in Python (so the exact bytes
are under our control) and recovered with a standard shell tool. In every case
the raw token is transformed, so it never appears as plaintext on disk.
"""

from __future__ import annotations

import base64
import bz2
import codecs
import gzip
import io
import lzma
import shlex
import tarfile
import zipfile

from .base import PlantContext, PlantResult, technique

B64 = lambda s: base64.b64encode(s.encode()).decode()  # noqa: E731

# ---------------------------------------------------------------- encodings ---


@technique("enc.base64", "encodings", "token base64-encoded in a file", tools=("base64",))
def enc_base64(ctx: PlantContext) -> PlantResult:
    name = ctx.rand_name("secret_", ".b64")
    ctx.write(name, B64(ctx.token) + "\n")
    # Read from stdin: BSD `base64` rejects a positional file argument, GNU accepts both.
    return PlantResult(f"base64 -d < {shlex.quote(name)}", [name])


@technique("enc.hex", "encodings", "token as a hex dump, reversed with xxd", tools=("xxd",))
def enc_hex(ctx: PlantContext) -> PlantResult:
    name = ctx.rand_name("dump_", ".hex")
    ctx.write(name, ctx.token.encode().hex() + "\n")
    return PlantResult(f"xxd -r -p {shlex.quote(name)}", [name])


@technique("enc.rot13", "encodings", "token ROT13-transformed, undone with tr")
def enc_rot13(ctx: PlantContext) -> PlantResult:
    name = ctx.rand_name("note_", ".txt")
    ctx.write(name, codecs.encode(ctx.token, "rot_13") + "\n")
    return PlantResult(f"tr 'A-Za-z' 'N-ZA-Mn-za-m' < {shlex.quote(name)}", [name])


@technique("enc.reversed", "encodings", "token reversed, undone with rev", tools=("rev",))
def enc_reversed(ctx: PlantContext) -> PlantResult:
    name = ctx.rand_name("mirror_", ".txt")
    ctx.write(name, ctx.token[::-1] + "\n")
    return PlantResult(f"rev {shlex.quote(name)}", [name])


@technique(
    "enc.base32", "encodings", "token base32-encoded (GNU coreutils)",
    tools=("base32",), platforms=("Linux",),
)
def enc_base32(ctx: PlantContext) -> PlantResult:
    name = ctx.rand_name("secret_", ".b32")
    ctx.write(name, base64.b32encode(ctx.token.encode()).decode() + "\n")
    return PlantResult(f"base32 -d {shlex.quote(name)}", [name])


# -------------------------------------------------------------- compression ---


# Compression of a short, high-entropy token can leave its bytes literal in the
# stream (small inputs are often stored raw), which the plaintext check rightly
# rejects. Compressing base64(token) keeps the *raw* token off disk for any token.


@technique("comp.gzip", "compression", "token gzip-compressed", tools=("gzip",))
def comp_gzip(ctx: PlantContext) -> PlantResult:
    name = ctx.rand_name("blob_", ".gz")
    ctx.write(name, gzip.compress(B64(ctx.token).encode()))
    return PlantResult(f"gzip -dc {shlex.quote(name)} | base64 -d", [name])


@technique("comp.bzip2", "compression", "token bzip2-compressed", tools=("bzip2",))
def comp_bzip2(ctx: PlantContext) -> PlantResult:
    name = ctx.rand_name("blob_", ".bz2")
    ctx.write(name, bz2.compress(B64(ctx.token).encode()))
    return PlantResult(f"bzip2 -dc {shlex.quote(name)} | base64 -d", [name])


@technique("comp.xz", "compression", "token xz/lzma-compressed", tools=("xz",))
def comp_xz(ctx: PlantContext) -> PlantResult:
    name = ctx.rand_name("blob_", ".xz")
    ctx.write(name, lzma.compress(B64(ctx.token).encode()))
    return PlantResult(f"xz -dc {shlex.quote(name)} | base64 -d", [name])


@technique("comp.gzip_double", "compression", "token gzip-compressed twice", tools=("gzip",))
def comp_gzip_double(ctx: PlantContext) -> PlantResult:
    name = ctx.rand_name("blob_", ".gz.gz")
    ctx.write(name, gzip.compress(gzip.compress(B64(ctx.token).encode())))
    return PlantResult(f"gzip -dc {shlex.quote(name)} | gzip -dc | base64 -d", [name])


# ------------------------------------------------------------------ archives ---


@technique("arc.tar", "archives", "token stored as a member inside a tar", tools=("tar",))
def arc_tar(ctx: PlantContext) -> PlantResult:
    name = ctx.rand_name("bundle_", ".tar")
    inner = ctx.rand_name("data/", ".txt")
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        payload = B64(ctx.token).encode()  # uncompressed tar stores members verbatim
        info = tarfile.TarInfo(inner)
        info.size = len(payload)
        tf.addfile(info, io.BytesIO(payload))
    ctx.write(name, buf.getvalue())
    return PlantResult(f"tar xOf {shlex.quote(name)} {shlex.quote(inner)} | base64 -d", [name])


@technique("arc.targz", "archives", "token inside a gzip-compressed tar", tools=("tar",))
def arc_targz(ctx: PlantContext) -> PlantResult:
    name = ctx.rand_name("bundle_", ".tar.gz")
    inner = ctx.rand_name("payload/", ".dat")
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        payload = B64(ctx.token).encode()
        info = tarfile.TarInfo(inner)
        info.size = len(payload)
        tf.addfile(info, io.BytesIO(payload))
    ctx.write(name, buf.getvalue())
    return PlantResult(f"tar xzOf {shlex.quote(name)} {shlex.quote(inner)} | base64 -d", [name])


@technique("arc.zip", "archives", "token stored as an entry inside a zip", tools=("unzip",))
def arc_zip(ctx: PlantContext) -> PlantResult:
    name = ctx.rand_name("archive_", ".zip")
    inner = ctx.rand_name("", ".txt")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(inner, B64(ctx.token))
    ctx.write(name, buf.getvalue())
    return PlantResult(f"unzip -p {shlex.quote(name)} {shlex.quote(inner)} | base64 -d", [name])
