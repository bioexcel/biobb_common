"""Module containing the function that records the provenance of a building block execution."""
import json
import re
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

from biobb_common.tools import file_utils as fu

# Lists where the paths of the written block crates are appended, one per active collect() context.
# A ContextVar, so blocks running in other threads are not collected (see collect).
_collectors: ContextVar[tuple[list[Path], ...]] = ContextVar("biobb_provenance_collectors", default=())
# Directory of the block crates without provenance_path property, set by the innermost collect() context
_default_dir: ContextVar[Optional[Path]] = ContextVar("biobb_provenance_dir", default=None)


@contextmanager
def collect(directory: Optional[Path] = None) -> Iterator[list[Path]]:
    """Enable the provenance of all the building blocks executed inside the
    context and collect the paths of their ro-crate-metadata.json files.

    Nested contexts collect the blocks of the inner contexts too. Blocks running
    in other threads are only collected if the thread runs in a copy of the
    context, ie: ``executor.submit(contextvars.copy_context().run, block, ...)``.

    Args:
        directory (Path): (None) Directory of the block crates of the blocks
            without provenance_path property, by default <path or cwd>/provenance.
    """
    collected: list[Path] = []
    token = _collectors.set(_collectors.get() + (collected,))
    dir_token = _default_dir.set(Path(directory).resolve()) if directory else None
    try:
        yield collected
    finally:
        if dir_token:
            _default_dir.reset(dir_token)
        _collectors.reset(token)


def track(obj, func: Callable, *args, **kwargs) -> Any:
    """Execute **func** and, if the **obj** has provenance enabled or runs inside
    a collect() context, write the RO-Crate of the execution. Errors writing the
    provenance are logged and never stop the building block.

    If the execution is skipped by the restart property, the latest crate of a
    previous execution of the same block with the same outputs is reused. If
    there is none, a crate of the skipped execution is written.

    Args:
        obj (BiobbObject): Building block being executed.
        func (Callable): Function to execute, usually obj.launch.
    """
    if not getattr(obj, "provenance", False) and not _collectors.get():
        return func(*args, **kwargs)

    # Same condition used by BiobbObject.check_restart to skip the execution
    skipped = getattr(obj, "restart", False) and fu.check_complete_files(obj.io_dict.get("out", {}).values())
    start_time = _now()
    try:
        value = func(*args, **kwargs)
    except Exception as error:
        _write(obj, start_time, error=error)
        raise
    _write(obj, start_time, return_value=value, skipped=skipped)
    return value


def provenance_dir(obj) -> Path:
    """Return the directory of the block RO-Crates: the provenance_path property, the
    directory of the active workflow_provenance context or <path or cwd>/provenance."""
    if getattr(obj, "provenance_path", None):
        return Path(obj.provenance_path).resolve()
    return _default_dir.get() or (Path(obj.path) if getattr(obj, "path", "") else Path.cwd()) / "provenance"


def crate_name(obj) -> str:
    """Return the prefix of the block crate directories: <step>_<ClassName> or <ClassName>."""
    step = re.sub(r"[^A-Za-z0-9.-]+", "_", str(getattr(obj, "step", "") or "")).strip("_")
    return f"{step}_{type(obj).__name__}" if step else type(obj).__name__


def crate_dir(obj, start_time: datetime) -> Path:
    """Return the directory of the block RO-Crate: <provenance_dir>/<crate_name>_<timestamp>"""
    return provenance_dir(obj) / f"{crate_name(obj)}_{start_time.strftime('%Y%m%d-%H%M%S-%f')}"


def previous_crate(obj) -> Optional[Path]:
    """Return the latest completed crate of the same block with the same outputs, if any."""
    # Imported here so rocrate is only loaded when provenance is enabled
    from biobb_common.provenance.crate import COMPLETED, as_list
    from biobb_common.provenance.record import output_uris

    outputs = output_uris(obj)
    for metadata_path in sorted(provenance_dir(obj).glob(f"{crate_name(obj)}_*/ro-crate-metadata.json"), reverse=True):
        try:
            graph = json.loads(metadata_path.read_text())["@graph"]
        except (OSError, ValueError, KeyError):
            continue
        for action in (e for e in graph if e.get("@type") == "CreateAction"):
            if action.get("actionStatus") == COMPLETED and {r["@id"] for r in as_list(action.get("result"))} == outputs:
                return metadata_path
    return None


def _write(obj, start_time: datetime, return_value: Any = None, error: Optional[BaseException] = None, skipped: bool = False) -> None:
    try:
        # Imported here so rocrate is only loaded when provenance is enabled
        from biobb_common.provenance.crate import write_block_crate
        from biobb_common.provenance.preview import write_preview
        from biobb_common.provenance.record import BlockRecord

        metadata_path = previous_crate(obj) if skipped else None
        if metadata_path:
            fu.log(f"Restart: reusing the provenance RO-Crate of the previous execution: {metadata_path}", obj.out_log, obj.global_log)
        else:
            record = BlockRecord.from_biobb_object(obj, start_time, _now(), return_value=return_value, error=error, skipped=skipped)
            metadata_path = write_block_crate(record, crate_dir(obj, start_time))
            write_preview(metadata_path.parent)
            fu.log(f"Provenance RO-Crate written to: {metadata_path}", obj.out_log, obj.global_log)
        for collected in _collectors.get():
            collected.append(metadata_path)
    except Exception as provenance_error:
        fu.log(f"WARNING: Provenance could not be written: {provenance_error}", obj.out_log, obj.global_log)


def _now() -> datetime:
    return datetime.now().astimezone()
