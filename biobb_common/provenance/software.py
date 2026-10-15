"""Module containing the functions to identify the software wrapped by a building block."""
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass
from functools import lru_cache
from importlib import metadata
from pathlib import Path
from typing import Optional

# Conda packages that are never the wrapped software, ie: binary_path: python
IGNORED_CONDA_PACKAGES = {"python", "bash", "coreutils"}
# Python or conda packages of the documented names that do not start with the package name.
# The longest documented name prefix (lower case) is used, otherwise the first word of the name.
PACKAGE_NAMES = {
    "pytorch": ("torch", "pytorch"),
    "open babel": ("openbabel",),
    "autodock vina": ("vina",),
    "haddock3-restraints": ("haddock3",),
    "haddock-restraints": ("haddock3",),
    "in house using biopython": ("biopython",),
    "structure checking from mdweb": ("biobb_structure_checking",),
    "mddb workflow": ("mddb_workflow",),
}


@dataclass
class WrappedSoftware:
    """Software wrapped by a building block.

    The version is detected from the first available source: container image
    tag, conda package owning the binary, Python distribution or conda package
    matching the name, and finally the version documented in the docstring.
    """
    name: str
    version: Optional[str]
    license: Optional[str] = None
    executable: Optional[str] = None
    package: Optional[str] = None
    # Web page of the package (anaconda.org, project home page or PyPI)
    url: Optional[str] = None
    # Documented version that is not an exact version, ie: ">=20.0"
    requirement: Optional[str] = None


def wrapped_software(obj) -> Optional[WrappedSoftware]:
    """Return the software wrapped by the **obj** building block, or None if
    the block does not document any wrapped software."""
    documented = documented_software(obj.__doc__)
    if not documented.get("name"):
        return None
    documented_version = documented.get("version")
    software = WrappedSoftware(
        name=documented["name"],
        # Ranges (ie: ">=20.0") are not versions, recorded as requirement only
        version=documented_version if is_version(documented_version) else None,
        license=documented.get("license"),
        requirement=None if is_version(documented_version) else documented_version,
    )

    # Container execution: the image tag is the best version information available,
    # tags that are not versions (ie: latest, serial) fall back to the documented version
    if getattr(obj, "container_path", None) and getattr(obj, "container_image", None):
        tag = image_tag(obj.container_image)
        if is_version(tag):
            software.version = tag
        return software

    # Local binary: conda package containing the executable.
    # Some blocks append flags to the binary path, ie: "gmx -nobackup -nocopyright"
    binary_path = str(getattr(obj, "binary_path", "") or "").split()
    executable = shutil.which(binary_path[0]) if binary_path else None
    if executable:
        software.executable = str(Path(executable).resolve())
        package = conda_package_of_file(executable)
        if package and package[0] not in IGNORED_CONDA_PACKAGES:
            software.package, software.version = package
            software.url = conda_package_url(str(Path(executable).resolve()), package[0])
            return software

    # Python library or conda package matching the documented name, ie: "Ambertools Cpptraj" -> "ambertools"
    for candidate in package_candidates(software.name):
        try:
            software.package, software.version = candidate, metadata.version(candidate)
            software.url = python_package_url(candidate)
            return software
        except metadata.PackageNotFoundError:
            pass
        version = conda_packages(sys.prefix).get(candidate)
        if version:
            software.package, software.version = candidate, version
            software.url = _conda_meta(sys.prefix)[2].get(candidate)
            return software

    return software


def is_version(value: Optional[str]) -> bool:
    """Return True if **value** is an exact version, ie: "2024.5", "v1.1.2", "2022.2--h1",
    not a range (">=20.0"), a text or a container tag like "latest" or "serial"."""
    return bool(value) and re.fullmatch(r"v?\d[\w.+-]*", str(value)) is not None


def package_candidates(name: str) -> tuple[str, ...]:
    """Return the Python or conda package names of a documented software name,
    ie: "PyTorch" -> ("torch", "pytorch"), "Ambertools Cpptraj" -> ("ambertools",)."""
    lower_name = name.lower()
    prefixes = [prefix for prefix in PACKAGE_NAMES if lower_name == prefix or lower_name.startswith(prefix + " ")]
    if prefixes:
        return PACKAGE_NAMES[max(prefixes, key=len)]
    return (lower_name.split()[0],)


def documented_software(doc: Optional[str]) -> dict[str, str]:
    """Return the name, version and license of the wrapped_software section of the docstring."""
    section = re.search(r"wrapped_software:(?P<section>(?:\s*\*\s*(?:name|version|license):.*)+)", str(doc))
    if not section:
        return {}
    software = {
        key.strip(): value.strip()
        for key, value in re.findall(r"\*\s*(\w+):(.*)", section.group("section"))
    }
    # "None" or "In house" mean that the block does not wrap any third-party software
    if software.get("name", "").lower() in ("none", "in house", ""):
        return {}
    return {key: value for key, value in software.items() if value.lower() != "none"}


def conda_package_url(file_path: str, name: str) -> Optional[str]:
    """Return the anaconda.org page of the conda package **name** of the environment containing **file_path**."""
    prefix = next((parent for parent in Path(file_path).parents if (parent / "conda-meta").is_dir()), None)
    return _conda_meta(str(prefix))[2].get(name) if prefix else None


def python_package_url(name: str) -> str:
    """Return the home page of a Python distribution, or its PyPI page."""
    meta = metadata.metadata(name)
    for project_url in meta.get_all("Project-URL") or []:
        label, _, url = project_url.partition(",")
        if label.strip().lower() in ("homepage", "home", "source", "repository") and url.strip():
            return url.strip()
    return meta.get("Home-page") or f"https://pypi.org/project/{meta.get('Name', name)}/"


def conda_package_of_file(file_path: str) -> Optional[tuple[str, str]]:
    """Return the (name, version) of the conda package that installed **file_path**."""
    path = Path(file_path).resolve()
    prefix = next((parent for parent in path.parents if (parent / "conda-meta").is_dir()), None)
    if prefix is None:
        return None
    return _conda_meta(str(prefix))[1].get(path.relative_to(prefix).as_posix())


def conda_packages(prefix: str) -> dict[str, str]:
    """Return the {name: version} of the packages installed in the conda environment **prefix**."""
    return _conda_meta(prefix)[0]


@lru_cache(maxsize=None)
def _conda_meta(prefix: str) -> tuple[dict[str, str], dict[str, tuple[str, str]], dict[str, str]]:
    """Read the conda-meta directory of the conda environment **prefix** once and return
    {package name: version}, {relative file path: (package name, version)} and
    {package name: anaconda.org page}."""
    packages: dict[str, str] = {}
    files: dict[str, tuple[str, str]] = {}
    urls: dict[str, str] = {}
    for meta_file in (Path(prefix) / "conda-meta").glob("*.json"):
        try:
            meta = json.loads(meta_file.read_text())
        except (OSError, ValueError):
            continue
        packages[meta["name"]] = meta["version"]
        # channel is a name (conda-forge) or a URL (https://conda.anaconda.org/conda-forge)
        channel = str(meta.get("channel") or "").rstrip("/").rsplit("/", 1)[-1]
        if channel:
            urls[meta["name"]] = f"https://anaconda.org/{channel}/{meta['name']}"
        for file_path in meta.get("files", []):
            files[file_path] = (meta["name"], meta["version"])
    return packages, files, urls


def image_tag(image: str) -> Optional[str]:
    """Return the tag of a container image, ie: "docker://gromacs/gromacs:2022.2" -> "2022.2".
    Local image files (ie: gromacs.sif) have no tag."""
    name = os.path.basename(image.split("@", 1)[0])
    if ":" not in name or Path(image).is_file():
        return None
    return name.rsplit(":", 1)[1]
