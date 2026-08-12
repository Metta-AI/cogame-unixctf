"""Filesystem-metadata, ELF, media and IPC families — the ones that hide the
token *off* the file's byte-content: in extended attributes, in a filename, in a
symlink target, in a binary's string table, in image metadata, or behind a live
IPC endpoint.
"""

from __future__ import annotations

import base64
import shlex
import subprocess
import time

from .base import PlantContext, PlantResult, technique

B64 = lambda s: base64.b64encode(s.encode()).decode()  # noqa: E731

# A minimal valid 1x1 PNG, used as a carrier for the media-metadata technique.
_PNG_1x1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


# ------------------------------------------------------------- fs_metadata ---


@technique(
    "fs.xattr_darwin", "fs_metadata", "base64 token in a user extended attribute (macOS)",
    tools=("xattr", "base64"), platforms=("Darwin",),
)
def fs_xattr_darwin(ctx: PlantContext) -> PlantResult:
    name = ctx.rand_name("cache_", ".bin")
    ctx.write(name, b"\x00cache entry\x00")
    subprocess.run(["xattr", "-w", "user.flag", B64(ctx.token), str(ctx.workdir / name)], check=True)
    return PlantResult(f"xattr -p user.flag {shlex.quote(name)} | base64 -d", [name])


@technique(
    "fs.xattr_linux", "fs_metadata", "base64 token in a user extended attribute (Linux)",
    tools=("setfattr", "getfattr", "base64"), platforms=("Linux",),
)
def fs_xattr_linux(ctx: PlantContext) -> PlantResult:
    name = ctx.rand_name("cache_", ".bin")
    ctx.write(name, b"\x00cache entry\x00")
    subprocess.run(
        ["setfattr", "-n", "user.flag", "-v", B64(ctx.token), str(ctx.workdir / name)], check=True
    )
    return PlantResult(
        f"getfattr --only-values -n user.flag {shlex.quote(name)} | base64 -d", [name]
    )


@technique("fs.filename_hex", "fs_metadata", "token hex-encoded as a filename", tools=("xxd",))
def fs_filename_hex(ctx: PlantContext) -> PlantResult:
    sub = ctx.rand_name("vault_")
    fname = ctx.token.encode().hex() + ".name"
    ctx.write(f"{sub}/{fname}", b"")
    return PlantResult(
        f"ls {shlex.quote(sub)} | sed 's/\\.name$//' | tr -d '\\n' | xxd -r -p", [f"{sub}/{fname}"]
    )


@technique("fs.symlink_target", "fs_metadata", "base64 token as a symlink target", tools=("readlink", "base64"))
def fs_symlink(ctx: PlantContext) -> PlantResult:
    import os

    link = ctx.rand_name("current_")
    target = B64(ctx.token)
    os.symlink(target, ctx.workdir / link)
    return PlantResult(f"readlink {shlex.quote(link)} | base64 -d", [link])


@technique("fs.deep_dotpath", "fs_metadata", "base64 token in a deeply nested dotdir", tools=("base64",))
def fs_deep(ctx: PlantContext) -> PlantResult:
    depth = ctx.rng.randint(3, 5)
    parts = ["." + ctx.rand_name() for _ in range(depth)]
    rel = "/".join(parts) + "/" + ctx.rand_name("state_", ".dat")
    ctx.write(rel, B64(ctx.token) + "\n")
    return PlantResult(f"cat {shlex.quote(rel)} | base64 -d", [rel])


# ------------------------------------------------------------ elf_internals ---


@technique(
    "elf.strings", "elf_internals", "base64 token embedded in a compiled binary's string table",
    tools=("gcc", "strings"),
)
def elf_strings(ctx: PlantContext) -> PlantResult:
    src = ctx.rand_name("prog_", ".c")
    binname = ctx.rand_name("prog_")
    ctx.write(src, f'#include <stdio.h>\nconst char* m="UNIXCTF:{B64(ctx.token)}";\nint main(){{return 0;}}\n')
    subprocess.run(["gcc", "-o", str(ctx.workdir / binname), str(ctx.workdir / src)], check=True, capture_output=True)
    return PlantResult(
        f"strings {shlex.quote(binname)} | grep '^UNIXCTF:' | cut -d: -f2 | base64 -d", [binname, src]
    )


# ----------------------------------------------------------- media_metadata ---


@technique(
    "media.exif_comment", "media_metadata", "base64 token in an image Comment tag",
    tools=("exiftool",),
)
def media_exif(ctx: PlantContext) -> PlantResult:
    name = ctx.rand_name("photo_", ".png")
    ctx.write(name, _PNG_1x1)
    subprocess.run(
        ["exiftool", "-overwrite_original", f"-Comment={B64(ctx.token)}", str(ctx.workdir / name)],
        check=True, capture_output=True,
    )
    return PlantResult(f"exiftool -s3 -Comment {shlex.quote(name)} | base64 -d", [name])


# ------------------------------------------------------------ processes_ipc ---


@technique(
    "ipc.fifo", "processes_ipc", "base64 token served on demand through a named pipe",
    tools=("base64", "mkfifo"), live=True,
)
def ipc_fifo(ctx: PlantContext) -> PlantResult:
    import os

    fifo = ctx.rand_name("chan_", ".fifo")
    fpath = ctx.workdir / fifo
    os.mkfifo(fpath)
    b64 = B64(ctx.token)
    # A background writer keeps re-offering the payload so the flag survives
    # repeated reads. start_new_session lets the Environment kill the group.
    ctx.spawn(["bash", "-c", f"while :; do printf %s {shlex.quote(b64)} > {shlex.quote(fifo)}; done"])
    time.sleep(0.05)
    return PlantResult(f"cat {shlex.quote(fifo)} | base64 -d", [fifo])
