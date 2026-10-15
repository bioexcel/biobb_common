# type: ignore
import hashlib
import json
import subprocess
from importlib import metadata

from biobb_common.provenance import environment
from biobb_common.provenance.crate import _image_reference
from biobb_common.provenance.environment import execution_environment
from biobb_common.provenance.record import image_digest
from biobb_common.provenance.software import conda_package_of_file, documented_software, image_tag, package_candidates, wrapped_software

DOC = """
    Info:
        * wrapped_software:
            * name: {name}
            * version: 2025.2
            * license: LGPL 2.1
        * ontology:
            * name: EDAM
            * schema: http://edamontology.org/EDAM.owl
"""


class FakeBlock:
    def __init__(self, name="GROMACS Pdb2gmx", binary_path="", container_path=None, container_image=""):
        self.__doc__ = DOC.format(name=name)
        self.binary_path = binary_path
        self.container_path = container_path
        self.container_image = container_image


def fake_conda_env(prefix):
    """Create a conda environment with a gromacs package installing bin/gmx."""
    (prefix / "conda-meta").mkdir()
    (prefix / "conda-meta" / "gromacs-2024.5-0.json").write_text(json.dumps(
        {"name": "gromacs", "version": "2024.5", "channel": "https://conda.anaconda.org/conda-forge",
         "files": ["bin/gmx", "share/gromacs/top/oplsaa.ff"]}))
    (prefix / "bin").mkdir()
    gmx = prefix / "bin" / "gmx"
    gmx.write_text("#!/bin/sh\n")
    gmx.chmod(0o755)
    return gmx


def test_documented_software():
    assert documented_software(DOC.format(name="GROMACS Pdb2gmx")) == {"name": "GROMACS Pdb2gmx", "version": "2025.2", "license": "LGPL 2.1"}
    assert documented_software(DOC.format(name="In house")) == {}
    assert documented_software(DOC.format(name="None")) == {}
    assert documented_software("No info section") == {}


def test_conda_package_of_file(tmp_path):
    gmx = fake_conda_env(tmp_path)
    assert conda_package_of_file(str(gmx)) == ("gromacs", "2024.5")
    assert conda_package_of_file(str(tmp_path / "bin" / "unknown")) is None


def test_wrapped_software_from_conda_binary(tmp_path):
    gmx = fake_conda_env(tmp_path)
    software = wrapped_software(FakeBlock(binary_path=str(gmx)))
    # Detected from conda, not the documented 2025.2
    assert (software.name, software.version) == ("GROMACS Pdb2gmx", "2024.5")
    assert software.package == "gromacs"
    assert software.executable == str(gmx.resolve())
    assert software.url == "https://anaconda.org/conda-forge/gromacs"
    # Flags appended to the binary path, ie: GROMACS blocks
    assert wrapped_software(FakeBlock(binary_path=f"{gmx} -nobackup -nocopyright")).version == "2024.5"


def test_wrapped_software_from_container(tmp_path):
    gmx = fake_conda_env(tmp_path)
    software = wrapped_software(FakeBlock(binary_path=str(gmx), container_path="/usr/bin/docker", container_image="gromacs/gromacs:2022.2"))
    assert software.version == "2022.2"
    # Image without tag or with a floating tag: documented version
    assert wrapped_software(FakeBlock(container_path="/usr/bin/docker", container_image="gromacs/gromacs")).version == "2025.2"
    assert wrapped_software(FakeBlock(container_path="/usr/bin/docker", container_image="gromacs/gromacs:latest")).version == "2025.2"


def test_image_tag(tmp_path):
    assert image_tag("docker://quay.io/biocontainers/gromacs:2022.2--h1") == "2022.2--h1"
    assert image_tag("localhost:5000/gromacs") is None
    assert image_tag("gromacs/gromacs:2022.2@sha256:abc") == "2022.2"
    sif = tmp_path / "gromacs:2022.sif"
    sif.write_text("image")
    assert image_tag(str(sif)) is None


def test_image_reference(tmp_path):
    assert _image_reference("gromacs/gromacs:2022.2") == {"registry": "docker.io", "name": "gromacs/gromacs", "tag": "2022.2"}
    assert _image_reference("docker://quay.io/biocontainers/gromacs:2022.2") == {"registry": "quay.io", "name": "biocontainers/gromacs", "tag": "2022.2"}
    assert _image_reference("localhost:5000/x/y") == {"registry": "localhost:5000", "name": "x/y"}
    sif = tmp_path / "gromacs.sif"
    sif.write_text("image")
    assert _image_reference(str(sif)) == {"name": "gromacs.sif"}


def test_image_digest(tmp_path):
    sif = tmp_path / "gromacs.sif"
    sif.write_text("image")
    assert image_digest("/usr/bin/singularity", str(sif)) == hashlib.sha256(b"image").hexdigest()
    assert image_digest("/usr/bin/singularity", "docker://gromacs/gromacs:2022.2") is None
    assert image_digest("/nonexistent/docker", "gromacs/gromacs:2022.2") is None


def test_package_candidates():
    assert package_candidates("PyTorch") == ("torch", "pytorch")
    assert package_candidates("Open Babel") == ("openbabel",)
    assert package_candidates("Haddock3-restraints") == ("haddock3",)
    assert package_candidates("In house using Biopython") == ("biopython",)
    assert package_candidates("Ambertools Cpptraj") == ("ambertools",)
    assert package_candidates("pytorchvideo") == ("pytorchvideo",)


def test_wrapped_software_from_python_distribution():
    software = wrapped_software(FakeBlock(name="rocrate"))
    assert software.version == metadata.version("rocrate")
    assert software.url.startswith("https://")


def test_wrapped_software_from_name_mapping():
    software = wrapped_software(FakeBlock(name="In house using Biopython"))
    assert (software.package, software.version) == ("biopython", metadata.version("biopython"))


def test_wrapped_software_from_documentation():
    software = wrapped_software(FakeBlock(name="Nonexistent Tool"))
    assert software.version == "2025.2"
    assert wrapped_software(FakeBlock(name="In house")) is None


def test_execution_environment():
    values = execution_environment()
    for key in ("operating_system", "architecture", "cpu_count", "python_version"):
        assert key in values
    assert not {"hostname", "user", "username"} & set(values)


def test_nvidia_gpus(monkeypatch):
    output = "NVIDIA A100-SXM4-40GB, 40960, 550.54.15\nNVIDIA A100-SXM4-40GB, 40960, 550.54.15\n"
    monkeypatch.setattr(environment.shutil, "which", lambda _: "/usr/bin/nvidia-smi")
    monkeypatch.setattr(environment.subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, stdout=output))
    assert environment._nvidia_gpus() == {
        "gpu_model": "NVIDIA A100-SXM4-40GB",
        "gpu_count": 2,
        "gpu_memory_bytes": 40960 * 1024 * 1024,
        "gpu_driver_version": "550.54.15",
    }
    monkeypatch.setattr(environment.shutil, "which", lambda _: None)
    assert environment._nvidia_gpus() == {}
