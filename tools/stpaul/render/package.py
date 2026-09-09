"""The week's whole package, as one archive.

A teacher who wants the week does not want twenty-four downloads. This
is the twelve PDFs, the twelve DOCX and the plain-text handoff in one
file, built in the same pass as its contents.

DETERMINISM, WHICH A ZIP DOES NOT GIVE YOU FOR FREE

A ZIP entry carries a modification time and a "created on" byte naming
the operating system that wrote it. Left alone, both vary: two builds a
minute apart differ, and a build on Windows differs from the same build
on Linux even when every archived byte is identical.

That is the same failure `hashing.normalize` exists to prevent, one
layer out, so it is fixed the same way. Every entry gets a fixed
timestamp and a fixed create_system, and the entries go in sorted order.
Two builds of the same approved bytes produce the same archive, byte for
byte, on either platform.
"""

from __future__ import annotations

import datetime as _dt
import zipfile
from pathlib import Path

# The earliest instant the ZIP format can express. Used only when there
# is no lesson date to reach for. What matters is that it is not a clock.
EPOCH = (1980, 1, 1, 0, 0, 0)


def date_time_for(d) -> tuple[int, int, int, int, int, int]:
    """A ZIP timestamp taken from the lesson's own date.

    Deterministic, because it is a property of the content rather than of
    when the build ran, and it reads correctly to a person: the week's
    package is dated the week's Sunday.
    """
    if isinstance(d, (_dt.date, _dt.datetime)):
        return (d.year, d.month, d.day, 0, 0, 0)
    return EPOCH

# 0 is MS-DOS/FAT. Python defaults this to 3 (Unix) when it writes on a
# Unix host and 0 on Windows, which is exactly the cross-platform drift
# this module is here to remove.
CREATE_SYSTEM = 0

# rw-r--r--, so the archive does not carry whatever umask the build ran
# under.
EXTERNAL_ATTR = 0o644 << 16


def build(entries: list[tuple[str, bytes]], out_path: Path,
          date_time: tuple = EPOCH) -> Path:
    """Write `entries` as (archive name, bytes) into a reproducible ZIP."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, data in sorted(entries, key=lambda e: e[0]):
            info = zipfile.ZipInfo(name, date_time=date_time)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = CREATE_SYSTEM
            info.external_attr = EXTERNAL_ATTR
            z.writestr(info, data)
    return out_path


def collect(out_dir: Path, subdirs: tuple[str, ...] = ("handouts", "handoff")) -> list[tuple[str, bytes]]:
    """Everything under `out_dir` worth handing to a teacher.

    The site's HTML and the app export are left out on purpose: this is
    the package someone prints from, not a copy of the web site.
    """
    entries: list[tuple[str, bytes]] = []
    for sub in subdirs:
        d = out_dir / sub
        if not d.is_dir():
            continue
        for f in sorted(p for p in d.rglob("*") if p.is_file()):
            entries.append((f.relative_to(out_dir).as_posix(), f.read_bytes()))
    return entries


def normalize(path: Path, date_time: tuple = EPOCH) -> Path:
    """Rewrite an existing ZIP with fixed entry metadata.

    For the DOCX files, which are ZIPs someone else wrote. python-docx
    saves through `ZipFile.writestr`, and that stamps every entry with
    the current local time, so two builds of the same approved content
    produced two different files. The words were identical and the bytes
    were not, which is precisely the thing this pipeline claims it can
    prove.

    Entry order is preserved rather than sorted: an OPC package is read
    by other people's software, and reordering its parts is a change this
    function has no reason to make.
    """
    with zipfile.ZipFile(path) as z:
        items = [(i, z.read(i.filename)) for i in z.infolist()]

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for info, data in items:
            fixed = zipfile.ZipInfo(info.filename, date_time=date_time)
            fixed.compress_type = zipfile.ZIP_DEFLATED
            fixed.create_system = CREATE_SYSTEM
            fixed.external_attr = EXTERNAL_ATTR
            z.writestr(fixed, data)
    return path


def write(out_dir: Path, slug: str, *, draft: bool = False,
          date_time: tuple = EPOCH) -> Path | None:
    """Archive a built Sunday. Returns None if there was nothing to archive."""
    entries = collect(out_dir)
    if not entries:
        return None
    name = f"{slug}-package" + ("-DRAFT" if draft else "") + ".zip"
    return build(entries, out_dir / name, date_time)
