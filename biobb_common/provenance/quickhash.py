"""Module containing the sampled xxHash quick-check of the files recorded in the provenance.

The quickhash identifies a file without reading it whole: it is the XXH3-128 (seed 0) of the file
size (uint64 big-endian) followed by three samples of 32 MiB at offsets 0, floor((size - n) / 2) and
size - n, or by the whole content when the file is smaller than 3 samples (96 MiB). It is an identity
check, not an integrity check: changes outside the samples go undetected. The sha256 stays the
authoritative digest of the files.

32 MiB samples hold complete frames of a 1 million atom trajectory in the usual formats (XTC ~3.8 MB
per frame, DCD, NetCDF or TRR ~12 MB), so a change to some atoms of every frame is detected, and the
structure and topology files (smaller than 96 MiB) are hashed whole.

The same scheme is implemented in the MDDB workflow (``mddb_workflow/utils/quickhash.py``), so its
files can be checked against the biobb provenance. Keep both implementations in sync: the tests of both check
them against the same golden vectors (``test/data/provenance/quickhash_golden.json``).
"""
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Optional, Union
from urllib.parse import unquote, urlsplit

import xxhash

ALGO = "xxh3_128-sample"
VERSION = 1
SAMPLE_SIZE = 1 << 25  # 32 MiB
# Read size of the samples, the files hashed whole and the sha256
CHUNK = 1 << 20

# Verification statuses
MATCH = "match"
SIZE_MISMATCH = "size_mismatch"
QUICKHASH_MISMATCH = "quickhash_mismatch"
SHA256_MISMATCH = "sha256_mismatch"
UNSUPPORTED_SCHEME = "unsupported_scheme"


def quickhash(path: Union[str, Path], sample_size: int = SAMPLE_SIZE) -> str:
    """Return the quickhash of a file: the lowercase hex XXH3-128 (seed 0) of its size as uint64
    big-endian, followed by its samples of **sample_size** bytes at 0, floor((size - n) / 2) and
    size - n (in that order, without separators), or by its whole content if it is smaller than
    3 samples. The samples never overlap nor run past the end of the file.

    Args:
        path (str, Path): Path to the file.
        sample_size (int): Size of the samples in bytes (n).

    Returns:
        str: 32 characters hex digest.

    Raises:
        OSError: If the file is shorter than its size when it is read (ie: truncated during the read).
    """
    if sample_size < 1:
        raise ValueError(f"The sample size must be positive: {sample_size}")
    size = os.path.getsize(path)
    hasher = xxhash.xxh3_128()
    hasher.update(size.to_bytes(8, "big"))
    with open(path, "rb") as file:
        if size < 3 * sample_size:
            _update(hasher, file, size)
        else:
            for offset in (0, (size - sample_size) // 2, size - sample_size):
                file.seek(offset)
                _update(hasher, file, sample_size)
    return hasher.hexdigest()


def quickhash_scheme(sample_size: int = SAMPLE_SIZE) -> dict[str, Any]:
    """Return the parameters of the quickhash scheme, stored with each value so the records are self-describing."""
    return {
        "algo": ALGO,
        "version": VERSION,
        "sample_size": sample_size,
        "positions": "0, floor((size-n)/2), size-n",
        "size_prefix": "uint64 big-endian",
        "small_file_rule": "size < 3n -> whole file",
    }


def quickhash_record(path: Union[str, Path], sample_size: int = SAMPLE_SIZE) -> dict[str, Any]:
    """Return the quickhash record of a file: the scheme parameters and its ``value``."""
    return {**quickhash_scheme(sample_size), "value": quickhash(path, sample_size)}


def sha256(path: Union[str, Path]) -> str:
    """Return the sha256 hex digest of a file, read in chunks."""
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_file(path: Union[str, Path], record: dict[str, Any], strict: bool = False) -> str:
    """Check that a file is the one described by its provenance record:
    ``{"contentSize": int, "sha256": str, "quickhash": {quickhash record}}``.

    1. If the size differs from ``contentSize``: ``size_mismatch``, without reading the file.
    2. If the quickhash scheme (``algo`` and ``version``) is not supported: ``unsupported_scheme``,
       or with **strict** the sha256 check (step 4).
    3. The quickhash is computed with the ``sample_size`` of the record, not the current default:
       ``quickhash_mismatch`` if it differs from its ``value``.
    4. With **strict**, the sha256 of the whole file: ``sha256_mismatch`` if it differs.

    Values missing in the record are not checked: without ``contentSize`` the size is not compared,
    and a strict check of a record without ``sha256`` only checks the quickhash.

    Args:
        path (str, Path): Path to the file.
        record (dict): Provenance record of the file.
        strict (bool): Also compare the sha256, which reads the whole file.

    Returns:
        str: ``match``, ``size_mismatch``, ``quickhash_mismatch``, ``sha256_mismatch`` or ``unsupported_scheme``.
    """
    if record.get("contentSize") is not None and os.path.getsize(path) != int(record["contentSize"]):
        return SIZE_MISMATCH
    scheme = record.get("quickhash")
    sample_size = _supported_sample_size(scheme)
    if sample_size is None:
        if not (strict and record.get("sha256")):
            return UNSUPPORTED_SCHEME
    elif quickhash(path, sample_size) != scheme["value"]:
        return QUICKHASH_MISMATCH
    if strict and record.get("sha256") and sha256(path) != record["sha256"]:
        return SHA256_MISMATCH
    return MATCH


def crate_file_records(crate_dir: Union[str, Path]) -> dict[Path, dict[str, Any]]:
    """Return the provenance records of the files of a block or workflow RO-Crate, by path.

    Files with a ``file://`` URI keep their absolute path, the others are relative to the crate directory.
    Left out: the files without size, sha256 nor quickhash (ie: README.md), directories, web resources
    and the earlier versions of the files written several times (ids with a fragment), which are no
    longer at their path.

    Args:
        crate_dir (str, Path): Directory containing the ro-crate-metadata.json file.

    Returns:
        dict: {path: {"contentSize": str, "sha256": str, "quickhash": {quickhash record}}}, with the recorded values only.
    """
    crate_dir = Path(crate_dir)
    graph = json.loads((crate_dir / "ro-crate-metadata.json").read_text(encoding="utf-8"))["@graph"]
    entities = {entity["@id"]: entity for entity in graph}
    records: dict[Path, dict[str, Any]] = {}
    for entity in graph:
        types = entity.get("@type")
        if "File" not in (types if isinstance(types, list) else [types]):
            continue
        url = urlsplit(entity["@id"])
        if url.fragment or (url.scheme and url.scheme != "file"):
            continue
        path = Path(unquote(url.path)) if url.scheme else crate_dir / unquote(entity["@id"])
        reference = entity.get("quickhash")
        record = {
            "contentSize": entity.get("contentSize"),
            "sha256": entity.get("sha256"),
            "quickhash": entities.get(reference["@id"]) if isinstance(reference, dict) else None,
        }
        record = {key: value for key, value in record.items() if value is not None}
        if record:
            records[path] = record
    return records


def _supported_sample_size(scheme: Any) -> Optional[int]:
    """Return the sample size of a quickhash record, None if its scheme is not supported."""
    if not isinstance(scheme, dict) or scheme.get("algo") != ALGO or str(scheme.get("version")) != str(VERSION) or not scheme.get("value"):
        return None
    try:
        sample_size = int(scheme.get("sample_size"))
    except (TypeError, ValueError):
        return None
    return sample_size if sample_size > 0 else None


def _update(hasher, file, size: int):
    """Hash exactly **size** bytes from the current position of **file**, read in chunks, so a file
    truncated during the read raises instead of hashing short data."""
    remaining = size
    while remaining:
        chunk = file.read(min(CHUNK, remaining))
        if not chunk:
            raise OSError(f"Unexpected end of file {getattr(file, 'name', '')}: wanted {size} bytes, got {size - remaining}")
        hasher.update(chunk)
        remaining -= len(chunk)
