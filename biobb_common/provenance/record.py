"""Module containing the provenance record of a single building block execution."""
import hashlib
import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from biobb_common.provenance.environment import execution_environment
from biobb_common.provenance.software import WrappedSoftware, wrapped_software


@dataclass
class FileRecord:
    """Input or output file (or directory) of a building block execution."""
    argument: str
    path: Path
    is_dir: bool
    edam_format: Optional[str] = None
    size: Optional[int] = None
    sha256: Optional[str] = None

    @property
    def uri(self) -> str:
        """Absolute file URI used as RO-Crate @id, directories end with '/'."""
        uri = self.path.as_uri()
        return uri + "/" if self.is_dir else uri


@dataclass
class BlockRecord:
    """Provenance data of a single building block execution."""
    class_name: str
    module: str
    package: str
    package_version: Optional[str]
    start_time: datetime
    end_time: datetime
    error: Optional[str] = None
    inputs: list[FileRecord] = field(default_factory=list)
    outputs: list[FileRecord] = field(default_factory=list)
    properties: dict[str, Any] = field(default_factory=dict)
    command_line: Optional[str] = None
    container_image: Optional[str] = None
    container_runtime: Optional[str] = None
    # sha256 digest of the container image, without the "sha256:" prefix
    container_digest: Optional[str] = None
    wrapped_software: Optional[WrappedSoftware] = None
    environment: dict[str, Any] = field(default_factory=dict)
    author: Optional[dict[str, str]] = None
    # Execution skipped by the restart property, the outputs come from a previous execution
    skipped: bool = False

    @property
    def completed(self) -> bool:
        return self.error is None

    @classmethod
    def from_biobb_object(cls, obj, start_time: datetime, end_time: datetime,
                          return_value: Any = None, error: Optional[BaseException] = None, skipped: bool = False) -> "BlockRecord":
        """Build the record from a BiobbObject after its launch() method has been executed.
        Skipped executions have no command line, wrapped software or environment."""
        error_str = None
        if error is not None:
            error_str = f"{type(error).__name__}: {error}"
        elif isinstance(return_value, int) and not isinstance(return_value, bool) and return_value != 0:
            error_str = f"Exit code: {return_value}"

        return cls(
            class_name=type(obj).__name__,
            module=type(obj).__module__,
            package=type(obj).__module__.split(".")[0],
            package_version=getattr(obj, "version", None),
            start_time=start_time,
            end_time=end_time,
            error=error_str,
            inputs=_file_records(obj, "in"),
            outputs=_file_records(obj, "out"),
            properties=_properties(obj),
            command_line=" ".join(map(str, obj.cmd)) if getattr(obj, "cmd", None) and not skipped else None,
            container_image=obj.container_image if getattr(obj, "container_path", None) else None,
            container_runtime=Path(obj.container_path).name if getattr(obj, "container_path", None) else None,
            container_digest=image_digest(obj.container_path, obj.container_image) if getattr(obj, "container_path", None) and not skipped else None,
            wrapped_software=None if skipped else wrapped_software(obj),
            environment={} if skipped else execution_environment(),
            author=_author(getattr(obj, "provenance_author", None)),
            skipped=skipped,
        )


def output_uris(obj) -> set[str]:
    """Return the URIs of the existing output files of a building block."""
    return {f.uri for f in _file_records(obj, "out")}


def image_digest(container_path: str, image: str) -> Optional[str]:
    """Return the sha256 digest of a container image: the repository digest of a
    Docker image (its id if it was never pulled from a registry) or the sha256 of
    a local image file (ie: Singularity .sif). None if it can not be found."""
    if not image:
        return None
    path = Path(image)
    if path.is_file():
        stat = path.resolve().stat()
        return _sha256(path.resolve(), stat.st_size, stat.st_mtime_ns)
    if not Path(container_path).name.startswith(("docker", "podman")):
        return None
    try:
        inspect = subprocess.run([container_path, "image", "inspect", "--format", "{{json .RepoDigests}} {{.Id}}", image],
                                 capture_output=True, text=True, timeout=60, check=True).stdout.split()
    except (OSError, subprocess.SubprocessError):
        return None
    repo_digests = (json.loads(inspect[0]) if inspect else None) or []
    digest = repo_digests[0].split("@", 1)[-1] if repo_digests else (inspect[1] if len(inspect) > 1 else "")
    return digest.removeprefix("sha256:") or None


def _file_records(obj, io: str) -> list[FileRecord]:
    checksum = getattr(obj, "provenance_checksum", False)
    records = []
    for argument, file_path in obj.io_dict.get(io, {}).items():
        if not file_path:
            # Optional file not set
            continue
        path = Path(file_path).resolve()
        if not path.exists():
            # ie: outputs of a failed execution
            continue
        doc = obj.doc_arguments_dict.get(argument, {})
        is_dir = doc.get("type") == "dir" or path.is_dir()
        records.append(FileRecord(
            argument=argument,
            path=path,
            is_dir=is_dir,
            edam_format=_edam_format(path, doc.get("formats", {}), is_dir),
            size=path.stat().st_size if path.is_file() else None,
            sha256=_sha256(path, path.stat().st_size, path.stat().st_mtime_ns) if checksum and path.is_file() else None,
        ))
    return records


@lru_cache(maxsize=None)
def _sha256(path: Path, size: int, mtime_ns: int) -> str:
    """Return the sha256 of a file. Size and modification time are part of the cache key,
    so the output of a step used as input of the next one is only read once."""
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _author(author: Any) -> Optional[dict[str, str]]:
    """Return the provenance_author property as a dict, a string is used as the name."""
    if not author:
        return None
    if isinstance(author, str):
        return {"name": author}
    return {key: str(value) for key, value in dict(author).items() if value}


def _edam_format(path: Path, formats: dict[str, str], is_dir: bool) -> Optional[str]:
    """Return the EDAM format id (ie: format_1476) matching the file extension."""
    if not formats:
        return None
    if len(formats) == 1 or is_dir:
        return next(iter(formats.values()))
    return formats.get(path.suffix.lstrip(".").lower())


def _properties(obj) -> dict[str, Any]:
    """Return the documented properties of the block with a JSON serializable value."""
    properties = {}
    for name in getattr(obj, "doc_properties_dict", {}):
        if not hasattr(obj, name):
            continue
        value = getattr(obj, name)
        if isinstance(value, Path):
            value = str(value)
        if value is None:
            continue
        try:
            json.dumps(value)
        except (TypeError, ValueError):
            continue
        properties[name] = value
    return properties
