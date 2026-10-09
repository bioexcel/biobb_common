# type: ignore
import hashlib
import json
from datetime import datetime
from importlib import metadata
from pathlib import Path
from types import SimpleNamespace

import pytest

from biobb_common.generic.folder_test import FolderTest, folder_test
from biobb_common.provenance import tracker
from biobb_common.provenance.crate import PROCESS_RUN_CRATE, as_list, write_block_crate
from biobb_common.provenance.graph import read_graph
from biobb_common.provenance.record import BlockRecord, _edam_format, _file_records
from biobb_common.tools import test_fixtures as fx
from biobb_common.tools.file_utils import launchlogger


class FailingFolderTest(FolderTest):
    __doc__ = FolderTest.__doc__

    @launchlogger
    def launch(self) -> int:
        raise RuntimeError("Something went wrong")


class WrappingFolderTest(FolderTest):
    """FolderTest documenting a wrapped software that is installed (rocrate)."""
    __doc__ = FolderTest.__doc__.replace("* name: None", "* name: rocrate").replace("* version: None", "* version: 0.0.1")


def read_crates(path, class_name="*"):
    """Return the block crates written in path, oldest first."""
    return [json.loads(p.read_text()) for p in sorted(Path(path).glob(f"provenance/{class_name}_*/ro-crate-metadata.json"))]


def entities(crate):
    return {e["@id"]: e for e in crate["@graph"]}


def actions(crate):
    return [e for e in crate["@graph"] if e["@type"] == "CreateAction"]


class TestBlockProvenance():
    def setup_class(self):
        fx.test_setup(self, 'provenance')

    def teardown_class(self):
        fx.test_teardown(self)

    def test_provenance_disabled(self):
        folder_test(properties=self.properties, **self.paths)
        assert not read_crates(self.properties['path'])

    def test_provenance_enabled(self):
        crates_before = len(read_crates(self.properties['path'], "FolderTest"))
        folder_test(properties={**self.properties, 'provenance': True}, **self.paths)
        crates = read_crates(self.properties['path'], "FolderTest")
        assert len(crates) == crates_before + 1
        crate = crates[-1]
        graph = entities(crate)

        assert graph["./"]["conformsTo"] == {"@id": PROCESS_RUN_CRATE}
        action, = actions(crate)
        assert action["actionStatus"] == "http://schema.org/CompletedActionStatus"
        assert action["startTime"] <= action["endTime"]

        instrument = graph[action["instrument"]["@id"]]
        assert instrument["@type"] == "SoftwareApplication"
        assert instrument["name"] == "biobb_common FolderTest"

        input_uri = Path(self.paths['input_folder']).resolve().as_uri() + "/"
        output_uri = Path(self.paths['output_folder']).resolve().as_uri() + "/"
        object_ids = [o["@id"] for o in as_list(action["object"])]
        assert input_uri in object_ids
        assert action["result"] == {"@id": output_uri}
        assert graph["./"]["mentions"] == {"@id": action["@id"]}
        assert graph[output_uri]["@type"] == "Dataset"
        assert graph[output_uri]["encodingFormat"] == "http://edamontology.org/format_1915"

        parameters = {graph[i]["name"]: graph[i]["value"] for i in object_ids if graph[i]["@type"] == "PropertyValue"}
        assert parameters["n"] == 2

        environment = {graph[e["@id"]]["name"]: graph[e["@id"]]["value"] for e in as_list(action["executionEnvironment"])}
        assert "architecture" in environment
        # FolderTest does not wrap any software
        assert "softwareRequirements" not in instrument

    def test_provenance_wrapped_software(self):
        WrappingFolderTest(properties={**self.properties, 'provenance': True}, **self.paths).launch()
        crate = read_crates(self.properties['path'], "WrappingFolderTest")[-1]
        graph = entities(crate)
        action, = actions(crate)
        instrument = graph[action["instrument"]["@id"]]
        software = graph[instrument["softwareRequirements"]["@id"]]
        assert software["@type"] == "SoftwareApplication"
        assert software["name"] == "rocrate"
        assert software["softwareVersion"] == metadata.version("rocrate")
        # Only the detected version, not the documented 0.0.1
        assert "0.0.1" not in json.dumps(software)
        assert set(crate["@context"][-1]) == {"executionEnvironment"}

    def test_provenance_failed_block(self):
        crates_before = len(read_crates(self.properties['path'], "FailingFolderTest"))
        with pytest.raises(RuntimeError):
            FailingFolderTest(properties={**self.properties, 'provenance': True},
                              input_folder=self.paths['input_folder'], output_folder="not_created").launch()
        crates = read_crates(self.properties['path'], "FailingFolderTest")
        assert len(crates) == crates_before + 1
        action, = actions(crates[-1])
        assert action["actionStatus"] == "http://schema.org/FailedActionStatus"
        assert action["error"] == "RuntimeError: Something went wrong"
        # Outputs not created are not recorded
        assert "result" not in action
        failed_crate_dir = sorted(Path(self.properties['path']).glob("provenance/FailingFolderTest_*"))[-1]
        assert read_graph(failed_crate_dir).steps[0].failed

    def test_provenance_author(self):
        author = {"name": "Jane Doe", "orcid": "https://orcid.org/0000-0002-1825-0097",
                  "affiliation": "IRB Barcelona", "affiliation_url": "https://www.irbbarcelona.org/"}
        folder_test(properties={**self.properties, 'provenance': True, 'provenance_author': author},
                    input_folder=self.paths['input_folder'], output_folder="author_out")
        crate = read_crates(self.properties['path'], "FolderTest")[-1]
        graph = entities(crate)
        action, = actions(crate)
        assert graph["./"]["author"] == {"@id": author["orcid"]}
        assert action["agent"] == {"@id": author["orcid"]}
        person = graph[author["orcid"]]
        assert (person["@type"], person["name"]) == ("Person", "Jane Doe")
        affiliation = graph[person["affiliation"]["@id"]]
        assert (affiliation["name"], affiliation["url"]) == ("IRB Barcelona", "https://www.irbbarcelona.org/")
        assert graph[graph["./"]["publisher"]["@id"]]["@type"] == "Organization"

    def test_restart_reuses_previous_crate(self):
        properties = {**self.properties, 'provenance': True}
        paths = {"input_folder": self.paths['input_folder'], "output_folder": "restart_out"}
        folder_test(properties=properties, **paths)
        crates_before = sorted(Path(self.properties['path']).glob("provenance/FolderTest_*"))
        with tracker.collect() as collected:
            folder_test(properties={**properties, 'restart': True}, **paths)
        # No new crate, the one of the previous execution is reused
        assert sorted(Path(self.properties['path']).glob("provenance/FolderTest_*")) == crates_before
        assert collected == [crates_before[-1] / "ro-crate-metadata.json"]

    def test_restart_without_previous_crate(self):
        # Outputs of an execution without provenance
        output_folder = Path(self.properties['path']) / "restart_no_crate_out"
        output_folder.mkdir()
        (output_folder / "file.txt").write_text("previous execution")
        folder_test(properties={**self.properties, 'provenance': True, 'restart': True},
                    input_folder=self.paths['input_folder'], output_folder=str(output_folder))
        action, = actions(read_crates(self.properties['path'], "FolderTest")[-1])
        assert action["description"].startswith("Skipped by the restart property")
        assert "executionEnvironment" not in action
        assert action["result"] == {"@id": output_folder.resolve().as_uri() + "/"}


def test_checksum(tmp_path):
    data = tmp_path / "data.txt"
    data.write_text("biobb")
    block = SimpleNamespace(io_dict={"in": {"input_path": str(data)}, "out": {}}, doc_arguments_dict={}, provenance_checksum=True)
    file_record, = _file_records(block, "in")
    assert file_record.sha256 == hashlib.sha256(b"biobb").hexdigest()
    block.provenance_checksum = False
    assert _file_records(block, "in")[0].sha256 is None

    record = BlockRecord(class_name="Test", module="biobb_test.test.test", package="biobb_test", package_version="1.0",
                         start_time=datetime.now().astimezone(), end_time=datetime.now().astimezone(), inputs=[file_record])
    graph = entities(json.loads(write_block_crate(record, tmp_path / "crate").read_text()))
    assert graph[data.as_uri()]["sha256"] == file_record.sha256


def test_edam_format():
    formats = {"pdb": "format_1476", "gro": "format_2033"}
    assert _edam_format(Path("structure.pdb"), formats, False) == "format_1476"
    assert _edam_format(Path("structure.GRO"), formats, False) == "format_2033"
    assert _edam_format(Path("structure.xyz"), formats, False) is None
    assert _edam_format(Path("topology.zip"), {"zip": "format_3987"}, False) == "format_3987"
    assert _edam_format(Path("structure.pdb"), {}, False) is None
