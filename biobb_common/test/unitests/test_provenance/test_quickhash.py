# type: ignore
"""Tests of the sampled xxHash quick-check of the provenance files.

The MDDB workflow implements the same scheme (mddb_workflow/utils/quickhash.py) and checks it against
the same golden vectors (test/data/provenance/quickhash_golden.json): keep both in sync.
"""
import hashlib
import importlib.util
import json
import os
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
import xxhash

from biobb_common.provenance import cli
from biobb_common.provenance import quickhash as qh
from biobb_common.provenance.crate import write_block_crate
from biobb_common.provenance.record import BlockRecord, _file_records
from biobb_common.provenance.workflow import merge_block_crates

GOLDEN = json.loads((Path(__file__).parents[2] / "data" / "provenance" / "quickhash_golden.json").read_text())
# Small sample size, so the files of the boundary tests are small
N = 16


def content(size: int) -> bytes:
    """Content of the golden vector files: bytes(range(256)) repeated and cut to size."""
    return (bytes(range(256)) * (size // 256 + 1))[:size]


def write_content(path, size: int):
    """Write the content of a golden vector file in 1 MiB blocks (a whole number of patterns), without holding it in memory."""
    block = bytes(range(256)) * 4096
    with open(path, "wb") as file:
        for start in range(0, size, len(block)):
            file.write(block[:size - start])
    return path


def write(path: Path, data: bytes) -> Path:
    path.write_bytes(data)
    return path


def flipped(data: bytes, offset: int) -> bytes:
    changed = bytearray(data)
    changed[offset] ^= 0xFF
    return bytes(changed)


def digest(data: bytes, hashed: bytes) -> str:
    """XXH64 of the size prefix of **data** followed by the **hashed** bytes: the hash of the sampled files."""
    return xxhash.xxh64_hexdigest(len(data).to_bytes(8, "big") + hashed)


@pytest.mark.parametrize("vector", GOLDEN["vectors"], ids=lambda v: f"size{v['size']}-n{v['sample_size']}")
def test_golden_vectors(tmp_path, vector):
    path = write_content(tmp_path / "file", vector["size"])
    assert qh.quickhash(str(path), vector["sample_size"]) == vector["quickhash"]
    # The largest ones are 128 MiB: not kept in the pytest temporary directories
    path.unlink()


def test_golden_scheme():
    """Same scheme and default sample size as the other implementation."""
    assert (GOLDEN["algo"], GOLDEN["version"], GOLDEN["default_sample_size"]) == (qh.ALGO, qh.VERSION, qh.SAMPLE_SIZE)


def test_small_files(tmp_path):
    """Files smaller than 3 samples: the plain XXH64 of the file, without size prefix (the hash of the MDDB cksum)."""
    for size in (0, 1, 2 * N, 3 * N - 1):
        data = content(size)
        assert qh.quickhash(write(tmp_path / "small", data), N) == xxhash.xxh64_hexdigest(data)
    # With the default sample size (32 MiB)
    assert qh.quickhash(write(tmp_path / "small", content(100))) == xxhash.xxh64_hexdigest(content(100))
    assert qh.quickhash(write(tmp_path / "empty", b"")) == "ef46db3751d8e999"


def test_boundary_sizes(tmp_path):
    # 3n - 1: whole file, without size prefix
    data = content(3 * N - 1)
    assert qh.quickhash(write(tmp_path / "small", data), N) == xxhash.xxh64_hexdigest(data)
    # 3n: the samples are exactly adjacent, they cover the whole file (after the size prefix)
    data = content(3 * N)
    assert qh.quickhash(write(tmp_path / "adjacent", data), N) == digest(data, data)
    # 3n + 1: middle sample at floor((2n + 1) / 2) = n, the byte at 2n is not sampled
    data = content(3 * N + 1)
    assert qh.quickhash(write(tmp_path / "odd", data), N) == digest(data, data[:2 * N] + data[2 * N + 1:])


def test_sensitivity_and_blind_spot(tmp_path):
    # Samples of a 167 bytes file: [0, 16), [75, 91) and [151, 167)
    data = content(10 * N + 7)
    original = qh.quickhash(write(tmp_path / "file", data), N)
    for offset in (5, 80, 160):
        assert qh.quickhash(write(tmp_path / "file", flipped(data, offset)), N) != original
    # Known blind spot: a change outside the samples is not detected
    assert qh.quickhash(write(tmp_path / "file", flipped(data, 40)), N) == original


def test_size_sensitivity(tmp_path):
    """Files with identical samples but different sizes."""
    assert qh.quickhash(write(tmp_path / "a", bytes(10 * N)), N) != qh.quickhash(write(tmp_path / "b", bytes(10 * N + 1)), N)


def test_determinism(tmp_path):
    path = write(tmp_path / "file", content(10 * N + 7))
    assert qh.quickhash(path, N) == qh.quickhash(path, N)


def test_parameter_round_trip(tmp_path):
    """A record written with a non-default sample size is verified with its sample size."""
    data = content(5 * 4096 + 3)
    path = write(tmp_path / "file", data)
    record = json.loads(json.dumps({"contentSize": len(data), "quickhash": qh.quickhash_record(path, 4096)}))
    assert record["quickhash"]["sample_size"] == 4096
    assert record["quickhash"]["value"] != qh.quickhash(path)
    assert qh.verify_file(path, record) == qh.MATCH


@pytest.mark.parametrize("size, claimed", [(10, 20), (40, 100)], ids=["whole-file", "samples"])
def test_truncated_during_read(tmp_path, monkeypatch, size, claimed):
    """A file shorter than its size when read raises instead of hashing short data."""
    path = write(tmp_path / "file", content(size))
    monkeypatch.setattr(os.path, "getsize", lambda _: claimed)
    with pytest.raises(OSError, match="Unexpected end of file"):
        qh.quickhash(path, N)


def test_verify_file(tmp_path, monkeypatch):
    data = content(10 * N + 7)
    path = write(tmp_path / "file", data)
    record = {"contentSize": str(len(data)), "sha256": hashlib.sha256(data).hexdigest(), "quickhash": qh.quickhash_record(path, N)}
    assert qh.verify_file(path, record) == qh.MATCH
    assert qh.verify_file(path, record, strict=True) == qh.MATCH
    # Byte changed in a sample
    write(path, flipped(data, 5))
    assert qh.verify_file(path, record) == qh.QUICKHASH_MISMATCH
    # Byte changed outside the samples: only the strict check finds it
    write(path, flipped(data, 40))
    assert qh.verify_file(path, record) == qh.MATCH
    assert qh.verify_file(path, record, strict=True) == qh.SHA256_MISMATCH
    # Unsupported schemes are reported, or checked with the sha256 when strict
    write(path, data)
    for scheme in (None, {**record["quickhash"], "algo": "imohash"}, {**record["quickhash"], "version": 2}, {**record["quickhash"], "sample_size": 0}):
        assert qh.verify_file(path, {**record, "quickhash": scheme}) == qh.UNSUPPORTED_SCHEME
        assert qh.verify_file(path, {**record, "quickhash": scheme}, strict=True) == qh.MATCH
    assert qh.verify_file(path, {"contentSize": len(data)}, strict=True) == qh.UNSUPPORTED_SCHEME
    # A different size is a mismatch without reading the file
    monkeypatch.setattr(qh, "open", lambda *_: pytest.fail("File read"), raising=False)
    assert qh.verify_file(path, {**record, "contentSize": 1}, strict=True) == qh.SIZE_MISMATCH


def test_crates(tmp_path):
    """The block and workflow crates record the quickhash, read back to verify the files."""
    data = write(tmp_path / "data.txt", b"biobb")
    block = SimpleNamespace(io_dict={"in": {"input_path": str(data)}, "out": {}}, doc_arguments_dict={}, provenance_checksum=True)
    file_record, = _file_records(block, "in")
    assert file_record.quickhash == qh.quickhash_record(data)
    block.provenance_checksum = False
    assert _file_records(block, "in")[0].quickhash is None

    record = BlockRecord(class_name="Test", module="biobb_test.test.test", package="biobb_test", package_version="1.0",
                         start_time=datetime.now().astimezone(), end_time=datetime.now().astimezone(), inputs=[file_record])
    block_crate = write_block_crate(record, tmp_path / "provenance" / "crate").parent
    graph = {e["@id"]: e for e in json.loads((block_crate / "ro-crate-metadata.json").read_text())["@graph"]}
    quickhash_id = "#quickhash-" + file_record.quickhash["value"]
    assert graph[data.as_uri()]["quickhash"] == {"@id": quickhash_id}
    assert graph[quickhash_id] == {"@id": quickhash_id, "@type": "PropertyValue", "name": "quickhash", **file_record.quickhash}
    # Workflow crate: the file inside the crate directory has a relative id
    merge_block_crates([block_crate / "ro-crate-metadata.json"], tmp_path)
    for crate_dir in (block_crate, tmp_path):
        records = qh.crate_file_records(crate_dir)
        assert list(records) == [data]
        assert records[data]["quickhash"]["value"] == file_record.quickhash["value"]
        assert qh.verify_file(data, records[data], strict=True) == qh.MATCH
        assert cli.main(["verify", str(crate_dir)]) == 0
        if importlib.util.find_spec("rocrate_validator"):
            from biobb_common.provenance.validation import validate_crate
            assert validate_crate(crate_dir) == []
    # Same size, other content
    data.write_bytes(b"biobc")
    assert qh.verify_file(data, qh.crate_file_records(tmp_path)[data]) == qh.QUICKHASH_MISMATCH
    assert cli.main(["verify", str(tmp_path)]) == 1
    data.unlink()
    assert cli.main(["verify", str(tmp_path)]) == 1
