"""Singularity/Apptainer image resolution (file_utils.get_singularity_image).

No real singularity is needed: CmdWrapper is replaced by a fake that records the
pull command and (optionally) creates the --name target like a successful pull.
"""
import shlex
from pathlib import Path

import pytest

from biobb_common.command_wrapper import cmd_wrapper
from biobb_common.generic.biobb_object import BiobbObject
from biobb_common.tools import file_utils as fu

GALAXY = "https://depot.galaxyproject.org/singularity/biobb_godmd:5.3.1--pyhdfd78af_0"
QUAY = "docker://quay.io/biocontainers/biobb_godmd:5.3.1--pyhdfd78af_0"
SIF = "biobb_godmd_5.3.1--pyhdfd78af_0.sif"


@pytest.mark.parametrize("ref, expected", [
    (GALAXY, SIF),
    (QUAY, SIF),
    ("quay.io/biocontainers/biobb_amber:5.3.3--py312hc5e4ab4_0", "biobb_amber_5.3.3--py312hc5e4ab4_0.sif"),
    ("https://example.org/images/tool.sif", "tool.sif"),
    ("library://user/col/img:1.0/", "img_1.0.sif"),
])
def test_sif_name(ref, expected):
    assert fu.singularity_sif_name(ref) == expected


def test_sif_name_keeps_versions_apart():
    a = fu.singularity_sif_name("https://x/biobb_analysis:5.3.0--pyhdfd78af_1")
    b = fu.singularity_sif_name("https://x/biobb_analysis:5.3.1--pyhdfd78af_0")
    assert a != b


class FakeWrapper:
    calls: list = []
    create = True
    return_code = 0

    def __init__(self, cmd, *args, **kwargs):
        self.cmd = cmd

    def launch(self):
        FakeWrapper.calls.append(self.cmd)
        if FakeWrapper.create:
            target = shlex.split(" ".join(self.cmd))[3]  # <bin> pull --name <target> <url>
            Path(target).write_text("fake image")
        return FakeWrapper.return_code


@pytest.fixture
def fake_pull(monkeypatch, tmp_path):
    FakeWrapper.calls = []
    FakeWrapper.create = True
    FakeWrapper.return_code = 0
    monkeypatch.setattr(cmd_wrapper, "CmdWrapper", FakeWrapper)
    images = tmp_path / "images dir"   # a space: the pull command must be quoted
    monkeypatch.setenv("BIOBB_SINGULARITY_DIR", str(images))
    return images


def test_images_dir_default(monkeypatch):
    monkeypatch.delenv("BIOBB_SINGULARITY_DIR", raising=False)
    assert fu.singularity_images_dir() == Path.home() / ".biobb" / "singularity"


def test_local_path_is_used_as_is(fake_pull, tmp_path):
    local = tmp_path / "my_image.sif"
    local.write_text("x")
    assert fu.get_singularity_image(str(local)) == str(local)
    assert FakeWrapper.calls == []


def test_pull_once_then_reuse(fake_pull):
    first = fu.get_singularity_image(GALAXY, "singularity")
    assert first == str(fake_pull / SIF)
    assert Path(first).read_text() == "fake image"
    assert len(FakeWrapper.calls) == 1
    cmd = shlex.split(" ".join(FakeWrapper.calls[0]))
    assert cmd[:3] == ["singularity", "pull", "--name"] and cmd[4] == GALAXY
    assert not list(fake_pull.glob("*.tmp-*"))          # temp file renamed away

    second = fu.get_singularity_image(QUAY, "apptainer")  # same image, other registry
    assert second == first
    assert len(FakeWrapper.calls) == 1                     # no second pull


def test_failed_pull_raises_and_leaves_nothing(fake_pull):
    FakeWrapper.return_code = 255
    with pytest.raises(FileNotFoundError, match="exit code 255"):
        fu.get_singularity_image(GALAXY)
    assert not list(fake_pull.iterdir())


def test_pull_without_output_raises(fake_pull):
    FakeWrapper.create = False
    with pytest.raises(FileNotFoundError):
        fu.get_singularity_image(GALAXY)


def test_create_cmd_line_uses_resolved_image(fake_pull):
    cmd = fu.create_cmd_line(["echo", "hi"], container_path="singularity",
                             host_volume="/tmp/sandbox", container_volume="/data",
                             container_shell_path="/bin/bash", container_image=GALAXY)
    assert str(fake_pull / SIF) in cmd
    assert GALAXY not in cmd


class Block(BiobbObject):
    """
    | biobb_common Block
    | Minimal block to build a container command line.

    Args:
        properties (dict - Python dictionary object containing the tool parameters, not input/output files):

    Examples:
        Block(properties={})
    """


def test_biobb_object_create_cmd_line_uses_resolved_image(fake_pull, tmp_path):
    # the code path every biobb tool takes (BiobbObject.create_cmd_line)
    obj = Block(properties={"container_path": "singularity", "container_image": GALAXY,
                            "container_shell_path": "/bin/bash", "disable_logs": True})
    obj.stage_io_dict = {"unique_dir": str(tmp_path)}
    obj.cmd = ["echo", "hi"]
    obj.create_cmd_line()
    assert obj.container_image == str(fake_pull / SIF)
    assert str(fake_pull / SIF) in obj.cmd
    assert len(FakeWrapper.calls) == 1
