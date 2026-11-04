# type: ignore
import getpass
import hashlib
import json
import os
import platform
import re
from datetime import datetime
from importlib import metadata
from pathlib import Path
from types import SimpleNamespace

import pytest

from biobb_common.generic.folder_test import FolderTest, folder_test
from biobb_common.provenance import tracker
from biobb_common.provenance.crate import PROCESS_RUN_CRATE, as_list, write_block_crate
from biobb_common.provenance.graph import read_graph, to_mermaid
from biobb_common.provenance.parameters import block_parameters, parse_mdp, parse_namelist
from biobb_common.provenance.record import BlockRecord, _edam_format, _file_records
from biobb_common.provenance.software import WrappedSoftware
from biobb_common.tools import test_fixtures as fx
from biobb_common.tools.file_utils import launchlogger


class FailingFolderTest(FolderTest):
    __doc__ = FolderTest.__doc__

    @launchlogger
    def launch(self) -> int:
        raise RuntimeError("Something went wrong")


class MdpFolderTest(FolderTest):
    """FolderTest generating a GROMACS mdp file in its sandbox, like grompp."""
    __doc__ = FolderTest.__doc__

    @launchlogger
    def launch(self) -> int:
        if self.check_restart():
            return 0
        self.stage_files()
        self.output_mdp_path = str(Path(self.stage_io_dict["unique_dir"]) / "grompp.mdp")
        Path(self.output_mdp_path).write_text("; Generated\nintegrator = md\nnsteps    = 500 ; steps\nref_t = 300 300\n")
        os.makedirs(self.stage_io_dict["out"]["output_folder"], exist_ok=True)
        self.copy_to_host()
        self.remove_tmp_files()
        return 0


class WrappingFolderTest(FolderTest):
    """FolderTest documenting a wrapped software that is installed (rocrate)."""
    __doc__ = FolderTest.__doc__.replace("* name: None", "* name: rocrate").replace("* version: None", "* version: 0.0.1")


def read_crates(path, class_name="*"):
    """Return the block crates written in path, oldest first."""
    return [json.loads((p / "ro-crate-metadata.json").read_text()) for p in crate_dirs(path, class_name)]


def crate_dirs(path, class_name="*"):
    """Return the block crate directories (<step>_<ClassName>_<timestamp>) written in path, oldest first."""
    pattern = re.compile(rf"^(.+_)?{'.+' if class_name == '*' else class_name}_\d{{8}}-")
    return sorted(p for p in Path(path).glob("provenance/*") if pattern.match(p.name))


def entities(crate):
    return {e["@id"]: e for e in crate["@graph"]}


def actions(crate):
    return [e for e in crate["@graph"] if e["@type"] == "CreateAction"]


def environment(crate):
    """Return the {name: value} of the execution environment of the block crate."""
    graph = entities(crate)
    action, = actions(crate)
    machine = graph[action["executionEnvironment"]["@id"]]
    return {graph[ref["@id"]]["name"]: graph[ref["@id"]]["value"] for ref in as_list(machine["valueReference"])}


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
        # Step name of the configuration, also in the crate directory name
        assert action["alternateName"] == "provenance"
        assert crate_dirs(self.properties['path'], "FolderTest")[-1].name.startswith("provenance_FolderTest_")

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
        assert graph[output_uri]["encodingFormat"] == {"@id": "http://edamontology.org/format_1915"}
        assert graph["http://edamontology.org/format_1915"]["@type"] == "WebSite"

        parameters = {graph[i]["name"]: graph[i]["value"] for i in object_ids if graph[i]["@type"] == "PropertyValue"}
        assert parameters["n"] == 2

        # One entity per machine, with the values as valueReference
        machine = graph[action["executionEnvironment"]["@id"]]
        assert machine["@type"] == "PropertyValue" and machine["@id"].startswith("#environment-")
        values = environment(crate)
        assert "architecture" in values
        # Hostname and username by default (provenance_user_host)
        assert values["hostname"] == platform.node()
        assert values["username"] == getpass.getuser()
        assert machine["value"].startswith(f"{getpass.getuser()}@{platform.node()}")
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
        assert software["@id"].startswith(software["url"] + "#") and software["url"].startswith("https://")
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
        failed_crate_dir = crate_dirs(self.properties['path'], "FailingFolderTest")[-1]
        assert read_graph(failed_crate_dir).steps[0].failed

    def test_provenance_user_host_disabled(self):
        folder_test(properties={**self.properties, 'provenance': True, 'provenance_user_host': False},
                    input_folder=self.paths['input_folder'], output_folder="no_user_host_out")
        crate = read_crates(self.properties['path'], "FolderTest")[-1]
        values = environment(crate)
        assert "architecture" in values
        assert not {"hostname", "username", "slurm_job_nodelist"} & set(values)
        assert platform.node() not in json.dumps(entities(crate)[actions(crate)[0]["executionEnvironment"]["@id"]])

    @pytest.mark.parametrize("remove_tmp", [True, False])
    def test_generated_parameters(self, remove_tmp):
        block = MdpFolderTest(properties={**self.properties, 'provenance': True, 'remove_tmp': remove_tmp},
                              input_folder=self.paths['input_folder'], output_folder="mdp_out")
        block.launch()
        # Removed with the sandbox: its parameters were read before. Kept: read when the crate is written.
        assert Path(block.output_mdp_path).exists() != remove_tmp
        crate = read_crates(self.properties['path'], "MdpFolderTest")[-1]
        graph = entities(crate)
        action, = actions(crate)
        mdp, = [graph[o["@id"]] for o in as_list(action["object"]) if graph[o["@id"]].get("name") == "grompp.mdp"]
        assert mdp["@type"] == "PropertyValue" and "generated by the building block" in mdp["description"]
        assert "subjectOf" not in mdp
        parameters = {graph[r["@id"]]["name"]: graph[r["@id"]]["value"] for r in as_list(mdp["valueReference"])}
        assert parameters == {"integrator": "md", "nsteps": 500, "ref_t": "300 300"}

    def test_provenance_path(self, tmp_path):
        folder_test(properties={**self.properties, 'provenance': True, 'provenance_path': str(tmp_path / "shared")},
                    input_folder=self.paths['input_folder'], output_folder="shared_out")
        crate_dir, = (tmp_path / "shared").iterdir()
        assert crate_dir.name.startswith("provenance_FolderTest_")
        assert (crate_dir / "ro-crate-metadata.json").exists()

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
        crates_before = crate_dirs(self.properties['path'], "FolderTest")
        with tracker.collect() as collected:
            folder_test(properties={**properties, 'restart': True}, **paths)
        # No new crate, the one of the previous execution is reused
        assert crate_dirs(self.properties['path'], "FolderTest") == crates_before
        assert collected == [crates_before[-1] / "ro-crate-metadata.json"]

    def test_restart_without_previous_crate(self):
        # Outputs of an execution without provenance
        output_folder = Path(self.properties['path']) / "restart_no_crate_out"
        output_folder.mkdir()
        (output_folder / "file.txt").write_text("previous execution")
        folder_test(properties={**self.properties, 'provenance': True, 'restart': True},
                    input_folder=self.paths['input_folder'], output_folder=str(output_folder))
        crate_dir = crate_dirs(self.properties['path'], "FolderTest")[-1]
        action, = actions(read_crates(self.properties['path'], "FolderTest")[-1])
        assert action["description"].startswith("Skipped by the restart property")
        assert "executionEnvironment" not in action
        assert action["result"] == {"@id": output_folder.resolve().as_uri() + "/"}
        # The start of the previous execution is unknown, the end is the last modification of the outputs
        assert "startTime" not in action
        assert datetime.fromisoformat(action["endTime"]).timestamp() == int((output_folder / "file.txt").stat().st_mtime)
        graph = read_graph(crate_dir)
        assert graph.steps[0].skipped
        assert ":::skipped" in to_mermaid(graph)
        assert "Skipped (restart)" in (crate_dir / "ro-crate-preview.html").read_text()


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


def test_file_arguments_outside_io_dict(tmp_path):
    """Documented file arguments that the block keeps outside io_dict are recorded, ie: grompp topology zip."""
    structure, topology = tmp_path / "structure.gro", tmp_path / "topology.zip"
    structure.write_text("gro")
    topology.write_text("zip")
    block = SimpleNamespace(
        io_dict={"in": {"input_gro_path": str(structure)}, "out": {}},
        input_top_zip_path=str(topology),
        doc_arguments_dict={
            "input_gro_path": {"input_output": "input", "formats": {"gro": "format_2033"}},
            "input_top_zip_path": {"input_output": "input", "formats": {"zip": "format_3987"}},
            "output_tpr_path": {"input_output": "output", "formats": {"tpr": "format_2333"}},
        },
    )
    records = {r.argument: r for r in _file_records(block, "in")}
    assert set(records) == {"input_gro_path", "input_top_zip_path"}
    assert (records["input_top_zip_path"].path, records["input_top_zip_path"].edam_format) == (topology, "format_3987")
    # Not set or not a path: ignored
    assert _file_records(block, "out") == []


def test_wrapped_software_requirement(tmp_path):
    record = BlockRecord(class_name="Test", module="biobb_test.test.test", package="biobb_test", package_version="1.0",
                         start_time=datetime.now().astimezone(), end_time=datetime.now().astimezone(),
                         wrapped_software=WrappedSoftware(name="AmberTools Reduce", version=None, requirement=">=20.0"))
    graph = entities(json.loads(write_block_crate(record, tmp_path / "crate").read_text()))
    software, = [e for e in graph.values() if e.get("name") == "AmberTools Reduce"]
    assert "softwareVersion" not in software
    assert software["description"] == "Version not detected, documented requirement: >=20.0"


def test_edam_format():
    formats = {"pdb": "format_1476", "gro": "format_2033"}
    assert _edam_format(Path("structure.pdb"), formats, False) == "format_1476"
    assert _edam_format(Path("structure.GRO"), formats, False) == "format_2033"
    assert _edam_format(Path("structure.xyz"), formats, False) is None
    assert _edam_format(Path("topology.zip"), {"zip": "format_3987"}, False) == "format_3987"
    assert _edam_format(Path("structure.pdb"), {}, False) is None


def test_parse_mdp():
    text = "; comment\ntitle = NVT ; equilibration\nnsteps = 50000\ndt = 0.002\ndefine = -DPOSRES\ntc-grps = Protein Non-Protein\nnsteps = 100\n\n"
    assert parse_mdp(text) == {"title": "NVT", "nsteps": 100, "dt": 0.002, "define": "-DPOSRES", "tc-grps": "Protein Non-Protein"}


def test_parse_namelist():
    text = """Heating, created by biobb_amber
 &cntrl
  imin = 0, nstlim = 5000, dt=0.002 ! time step
  ntb=1 ntp=0,
  restraintmask = ':1-100@CA & !@H=', restraint_wt=2.0,
  inf = nan,
 /
 &wt type='TEMP0', istep1=0, istep2=5000, value1=0.0, value2=300.0 /
 &wt type='END' /
Hold the protein
10.0
RES 1 100
END
"""
    assert parse_namelist(text) == {
        "cntrl.imin": 0, "cntrl.nstlim": 5000, "cntrl.dt": 0.002, "cntrl.ntb": 1, "cntrl.ntp": 0,
        "cntrl.restraintmask": ":1-100@CA & !@H=", "cntrl.restraint_wt": 2.0, "cntrl.inf": "nan",
        "wt[1].type": "TEMP0", "wt[1].istep1": 0, "wt[1].istep2": 5000, "wt[1].value1": 0.0, "wt[1].value2": 300.0,
        "wt[2].type": "END",
    }
    # &end terminator, and scripts that are not namelists (ie: tleap)
    assert parse_namelist("&cntrl\n imin=1,\n&end\n") == {"cntrl.imin": 1}
    assert parse_namelist("source leaprc.protein.ff14SB\nsaveamberparm mol top.prmtop crd.inpcrd\nquit\n") == {}


def test_input_parameters(tmp_path):
    """Without generated parameter files, the input parameter files are parsed and linked with subjectOf."""
    mdin, leap = tmp_path / "npt.mdin", tmp_path / "leap.in"
    mdin.write_text("&cntrl\n imin = 0, nstlim = 5000\n/\n")
    leap.write_text("quit\n")
    block = SimpleNamespace(io_dict={"in": {"input_mdin_path": str(mdin), "input_leap_path": str(leap)}, "out": {}}, doc_arguments_dict={})
    parameter_set, = block_parameters(block)
    assert (parameter_set.name, parameter_set.generated, parameter_set.path) == ("npt.mdin", False, mdin)
    assert parameter_set.values == {"cntrl.imin": 0, "cntrl.nstlim": 5000}

    record = BlockRecord(class_name="Test", module="biobb_test.test.test", package="biobb_test", package_version="1.0",
                         start_time=datetime.now().astimezone(), end_time=datetime.now().astimezone(), parameters=[parameter_set])
    graph = entities(json.loads(write_block_crate(record, tmp_path / "crate").read_text()))
    group, = [e for e in graph.values() if e.get("name") == "npt.mdin"]
    assert group["subjectOf"] == {"@id": mdin.as_uri()}
    assert group["value"] == "2 parameters"
