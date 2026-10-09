# type: ignore
import contextvars
import json
import shutil
import threading
from pathlib import Path

import pytest

from biobb_common import biobb_global_properties
from biobb_common.generic.folder_test import folder_test
from biobb_common.provenance import find_block_crates, merge_block_crates, workflow_provenance
from biobb_common.provenance import cli
from biobb_common.provenance.crate import as_list
from biobb_common.provenance.graph import read_graph, to_mermaid, write_graph
from biobb_common.provenance.preview import GENERATED_MARK
from biobb_common.provenance.workflow import _web_url
from biobb_common.tools import test_fixtures as fx


def entities(metadata_path):
    return {e["@id"]: e for e in json.loads(Path(metadata_path).read_text())["@graph"]}


def of_type(graph, entity_type):
    return [e for e in graph.values() if entity_type in e["@type"]]


ORCID = "https://orcid.org/0000-0002-1825-0097"


class TestWorkflowProvenance():
    def setup_class(self):
        fx.test_setup(self, 'workflow_provenance')
        self.input_uri = Path(self.paths['input_folder']).resolve().as_uri() + "/"
        self.properties = {**self.properties, "provenance_author": {"name": "Jane Doe", "orcid": ORCID}}
        # Two chained steps: input_folder -> step1_out -> step2_out
        with workflow_provenance(path=self.properties['path'], name="test workflow", workflow_file=__file__, license="MIT"):
            folder_test(input_folder=self.paths['input_folder'], output_folder="step1_out", properties=self.properties)
            folder_test(input_folder="step1_out", output_folder="step2_out", properties=self.properties)

    def teardown_class(self):
        fx.test_teardown(self)

    def test_global_property_untouched(self):
        assert "provenance" not in biobb_global_properties

    def test_license_global_property(self, tmp_path):
        biobb_global_properties["provenance_license"] = "Apache-2.0"
        try:
            with workflow_provenance(path=tmp_path, workflow_file=__file__):
                folder_test(input_folder=self.paths['input_folder'], output_folder=str(tmp_path / "out"), properties={"path": str(tmp_path)})
        finally:
            biobb_global_properties.pop("provenance_license")
        workflow = entities(tmp_path / "ro-crate-metadata.json")[Path(__file__).name]
        assert workflow["license"] == {"@id": "https://spdx.org/licenses/Apache-2.0"}

    def test_threads(self, tmp_path):
        def run(output_folder):
            folder_test(input_folder=self.paths['input_folder'], output_folder=str(tmp_path / output_folder), properties={"path": str(tmp_path)})

        with workflow_provenance(path=tmp_path / "wf", workflow_file=__file__):
            # Not collected (and provenance not enabled) in other threads unless they run in a copy of the context
            thread = threading.Thread(target=run, args=("other_thread",))
            thread.start()
            thread.join()
            thread = threading.Thread(target=contextvars.copy_context().run, args=(run, "copied_context"))
            thread.start()
            thread.join()
        graph = entities(tmp_path / "wf" / "ro-crate-metadata.json")
        assert len(of_type(graph, "HowToStep")) == 1
        assert (tmp_path / "copied_context").as_uri() + "/" in graph

    def test_nested(self, tmp_path):
        with workflow_provenance(path=tmp_path / "outer", workflow_file=__file__):
            folder_test(input_folder=self.paths['input_folder'], output_folder=str(tmp_path / "out1"), properties={"path": str(tmp_path)})
            with workflow_provenance(path=tmp_path / "inner", workflow_file=__file__):
                folder_test(input_folder=str(tmp_path / "out1"), output_folder=str(tmp_path / "out2"), properties={"path": str(tmp_path)})
        assert len(of_type(entities(tmp_path / "inner" / "ro-crate-metadata.json"), "HowToStep")) == 1
        assert len(of_type(entities(tmp_path / "outer" / "ro-crate-metadata.json"), "HowToStep")) == 2

    def test_block_crates(self):
        assert len(find_block_crates(self.properties['path'])) == 2

    def test_workflow_crate(self):
        graph = entities(Path(self.properties['path']) / "ro-crate-metadata.json")
        root = graph["./"]
        assert {p["@id"] for p in root["conformsTo"]} >= {
            "https://w3id.org/ro/wfrun/process/0.5",
            "https://w3id.org/ro/wfrun/workflow/0.5",
            "https://w3id.org/ro/wfrun/provenance/0.5",
        }
        workflow = graph[root["mainEntity"]["@id"]]
        assert "ComputationalWorkflow" in workflow["@type"]
        # The workflow script is copied into the crate
        assert workflow["@id"] == Path(__file__).name
        assert (Path(self.properties['path']) / Path(__file__).name).exists()
        assert workflow["name"] == "test workflow"
        # Bioschemas ComputationalWorkflow
        assert workflow["conformsTo"] == {"@id": "https://bioschemas.org/profiles/ComputationalWorkflow/1.0-RELEASE"}
        assert workflow["version"] and workflow["url"] and workflow["dateCreated"]
        assert workflow["creator"] == {"@id": ORCID}
        assert workflow["sdPublisher"] == {"@id": "https://bioexcel.eu/"}
        assert graph[workflow["license"]["@id"]]["identifier"] == "MIT"
        workflow_input, workflow_output = graph[workflow["input"]["@id"]], graph[workflow["output"]["@id"]]
        assert (workflow_input["@type"], workflow_input["additionalType"]) == ("FormalParameter", "Dataset")
        assert graph[self.input_uri]["exampleOfWork"] == {"@id": workflow_input["@id"]}
        assert graph["step2_out/"]["exampleOfWork"] == {"@id": workflow_output["@id"]}
        steps = [graph[s["@id"]] for s in workflow["step"]]
        assert [s["position"] for s in steps] == ["0", "1"]

        workflow_action = graph["#workflow-run"]
        assert len(root["mentions"]) == 3
        assert workflow_action["instrument"] == {"@id": workflow["@id"]}
        assert workflow_action["actionStatus"] == "http://schema.org/CompletedActionStatus"
        assert workflow_action["object"] == {"@id": self.input_uri}
        assert workflow_action["result"] == {"@id": "step2_out/"}

        # The output of the first step is the input of the second one: relative id, single entity
        step_actions = [graph[c["object"]["@id"]] for c in of_type(graph, "ControlAction")]
        assert len(step_actions) == 2
        assert {"@id": "step1_out/"} in as_list(step_actions[0]["result"])
        assert {"@id": "step1_out/"} in as_list(step_actions[1]["object"])
        assert graph["step1_out/"]["@type"] == "Dataset"
        assert {"@id": "step1_out/"} in root["hasPart"]

        # The author of the steps is the author of the workflow crate
        assert root["author"] == {"@id": ORCID}
        assert workflow_action["agent"] == {"@id": ORCID}

        organize, = of_type(graph, "OrganizeAction")
        assert organize["result"] == {"@id": workflow_action["@id"]}
        assert len(organize["object"]) == 2

    def test_readme_and_preview(self, tmp_path):
        path = Path(self.properties['path'])
        graph = entities(path / "ro-crate-metadata.json")
        assert graph["README.md"]["encodingFormat"] == "text/markdown"
        assert graph["README.md"]["about"] == {"@id": "./"}
        readme = (path / "README.md").read_text()
        assert "# test workflow" in readme and "```mermaid" in readme
        preview = (path / "ro-crate-preview.html").read_text()
        assert preview.startswith(GENERATED_MARK) and "test workflow" in preview
        # Block crates have a preview too
        assert all((p.parent / "ro-crate-preview.html").exists() for p in find_block_crates(path))
        # README.md files not written by biobb are kept and not described in the crate
        (tmp_path / "README.md").write_text("# My project\n")
        merge_block_crates(find_block_crates(path), tmp_path)
        assert (tmp_path / "README.md").read_text() == "# My project\n"
        assert "README.md" not in entities(tmp_path / "ro-crate-metadata.json")

    def test_web_url(self):
        assert _web_url("git@github.com:bioexcel/biobb_wf.git") == "https://github.com/bioexcel/biobb_wf"
        assert _web_url("https://user:token@gitlab.com/group/repo.git/") == "https://gitlab.com/group/repo"
        assert _web_url("ssh://git@github.com/bioexcel/biobb_wf.git") == "https://github.com/bioexcel/biobb_wf"

    def test_offline_merge(self, tmp_path):
        metadata_path = merge_block_crates(find_block_crates(self.properties['path']), tmp_path)
        graph = entities(metadata_path)
        assert len(of_type(graph, "HowToStep")) == 2
        assert "license" not in graph["#workflow"]
        # Without workflow script: only a Process Run Crate, the steps are still recorded
        assert graph["./"]["conformsTo"] == {"@id": "https://w3id.org/ro/wfrun/process/0.5"}
        assert "mainEntity" not in graph["./"]
        assert graph["#workflow-run"]["instrument"] == {"@id": "#workflow"}
        assert len(read_graph(tmp_path).steps) == 2
        # Files outside the output directory keep their absolute file URI
        step1_uri = (Path(self.properties['path']) / "step1_out").resolve().as_uri() + "/"
        assert graph[step1_uri]["@type"] == "Dataset"

    def test_graph(self):
        graph = read_graph(self.properties['path'])
        assert [s.label for s in graph.steps] == ["1: FolderTest", "2: FolderTest"]
        assert sorted(graph.files.values()) == ["input_folder", "step1_out", "step2_out"]
        step0, step1 = (s.id for s in graph.steps)
        assert graph.edges == [(self.input_uri, step0), (step0, "step1_out/"), ("step1_out/", step1), (step1, "step2_out/")]
        mermaid = to_mermaid(graph)
        assert mermaid.startswith("flowchart TD")
        assert "file1 --> step1" in mermaid

    def test_write_graph(self, tmp_path):
        assert write_graph(self.properties['path'], tmp_path / "graph.dot").read_text().startswith("digraph provenance {")
        assert write_graph(self.properties['path'], tmp_path / "graph.md").read_text().startswith("```mermaid")
        pytest.importorskip("graphviz")
        if not shutil.which("dot"):
            pytest.skip("Graphviz binaries not installed")
        assert write_graph(self.properties['path'], tmp_path / "graph.svg").read_text().count("<svg") == 1

    def test_cli(self, tmp_path, capsys):
        assert cli.main(["merge", self.properties['path'], "-o", str(tmp_path), "-w", __file__, "-l", "https://example.org/license"]) == 0
        workflow = entities(tmp_path / "ro-crate-metadata.json")[Path(__file__).name]
        assert workflow["license"] == {"@id": "https://example.org/license"}
        assert (tmp_path / "ro-crate-metadata.json").exists()
        assert cli.main(["graph", str(tmp_path)]) == 0
        assert "step1_out" in capsys.readouterr().out
        assert cli.main(["merge", str(tmp_path / "empty"), "-o", str(tmp_path)]) == 1

    def test_validation(self, tmp_path):
        pytest.importorskip("rocrate_validator")
        from biobb_common.provenance.validation import validate_crate
        assert validate_crate(self.properties['path']) == []
        assert validate_crate(find_block_crates(self.properties['path'])[0].parent) == []
        merge_block_crates(find_block_crates(self.properties['path']), tmp_path)
        assert validate_crate(tmp_path) == []
