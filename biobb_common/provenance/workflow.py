"""Module containing the functions to build the workflow RO-Crate from the building block RO-Crates."""
import hashlib
import json
import platform
import re
import shutil
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterator, Optional, Union
from urllib.parse import unquote, urlsplit, urlunsplit

from rocrate.model.contextentity import ContextEntity
from rocrate.rocrate import ROCrate

from biobb_common import __version__, biobb_global_properties
from biobb_common.provenance import tracker
from biobb_common.provenance.crate import (COMPLETED, FAILED, LICENSE, PROCESS_RUN_CRATE, PUBLISHER, RESTART_SKIPPED, action_time, as_list, iso,
                                           is_restart_skipped, new_crate, parse_time, single, software_version)
from biobb_common.provenance.preview import PREVIEW, README, is_generated, write_preview, write_readme

WORKFLOW_RO_CRATE = "https://w3id.org/workflowhub/workflow-ro-crate/1.0"
COMPUTATIONAL_WORKFLOW = "https://bioschemas.org/profiles/ComputationalWorkflow/1.0-RELEASE"
FORMAL_PARAMETER = "https://bioschemas.org/profiles/FormalParameter/1.0-RELEASE"
PROFILES = {
    PROCESS_RUN_CRATE: ("Process Run Crate", "0.5"),
    "https://w3id.org/ro/wfrun/workflow/0.5": ("Workflow Run Crate", "0.5"),
    "https://w3id.org/ro/wfrun/provenance/0.5": ("Provenance Run Crate", "0.5"),
    WORKFLOW_RO_CRATE: ("Workflow RO-Crate", "1.0"),
}
# Entities of the block crates that are replaced by the ones of the workflow crate
SKIPPED_IDS = {"./", "ro-crate-metadata.json", LICENSE, PUBLISHER, README, PREVIEW, *PROFILES}


def find_block_crates(directory: Union[str, Path]) -> list[Path]:
    """Return the block ro-crate-metadata.json files found inside **directory**."""
    return sorted(Path(directory).glob("**/provenance/*/ro-crate-metadata.json"))


def merge_block_crates(block_crates: list[Union[str, Path]], output_dir: Union[str, Path],
                       workflow_file: Optional[Union[str, Path]] = None, name: Optional[str] = None,
                       license: Optional[str] = None, path_map: Optional[dict[str, str]] = None) -> Path:
    """Merge building block RO-Crates into a workflow RO-Crate (Provenance Run Crate profile).

    The steps are ordered by start time (end time for the steps skipped by the
    restart property) and, if their times are equal (crates of previous versions
    record seconds), by the start time with microseconds in the name of their
    crate directory. They are linked through their files: the output of a step with
    the same path as the input of another step is the same entity. Steps run on
    other machines (ie: an HPC cluster) are linked with **path_map**, which
    replaces the beginning of their paths, or by checksum (provenance_checksum
    property): an input that no step produced is the output of a previous step
    with the same sha256. Without **workflow_file** (ie: Jupyter notebooks) the crate only
    conforms to the Process Run Crate profile, because a Workflow RO-Crate
    requires the workflow file. Files inside **output_dir** get relative ids, so the workflow crate
    can be moved together with its files. The workflow file is copied into
    **output_dir** if it is not already inside it. A README.md and a
    ro-crate-preview.html are written too, unless files with these names not
    written by biobb already exist in **output_dir**.

    Args:
        block_crates (list): Paths to the block ro-crate-metadata.json files or their directories.
        output_dir (str, Path): Directory where the workflow ro-crate-metadata.json will be written.
        workflow_file (str, Path): (None) Python script of the workflow.
        name (str): (None) Name of the workflow, by default the workflow file name.
        license (str): (None) License of the workflow script: SPDX identifier (ie: "MIT") or URL.
        path_map (dict): (None) {path in the block crates: path in this machine}, ie:
            {"/gpfs/scratch/user/wf": "/home/user/wf"}, applied to the file ids before linking the steps.
            Files that do not exist at the new path (ie: not copied back) keep their original id.

    Returns:
        Path: Path to the written ro-crate-metadata.json file.
    """
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    uri_map = {_uri(old): _uri(new) for old, new in (path_map or {}).items()}
    entities: dict[str, dict] = {}
    # Execution order of the block crates (directory name), to order the steps with equal times
    crate_ranks = {index: rank for rank, index in enumerate(sorted(range(len(block_crates)), key=lambda i: _crate_start(block_crates[i])))}
    action_ranks: dict[str, int] = {}
    for index, block_crate in enumerate(block_crates):
        for entity in _read_graph(block_crate):
            entity = _relativize(_replace_ids(entity, uri_map, prefix=True), output_dir)
            if entity["@id"] in SKIPPED_IDS:
                continue
            if entity["@type"] == "CreateAction":
                action_ranks[entity["@id"]] = crate_ranks[index]
            entities.setdefault(entity["@id"], {}).update(entity)

    def order(action: dict) -> tuple:
        return action_time(action), action_ranks.get(action["@id"], -1)

    entities = _link_by_checksum(entities, order)
    step_actions = sorted((e for e in entities.values() if e["@type"] == "CreateAction"), key=order)

    name = name or (Path(workflow_file).stem if workflow_file else "biobb workflow")
    # Without a workflow script the crate can not be a Workflow RO-Crate (its mainEntity must be
    # a File of the crate), so it only conforms to Process Run Crate. The steps are still recorded.
    profiles = PROFILES if workflow_file else {PROCESS_RUN_CRATE: PROFILES[PROCESS_RUN_CRATE]}
    crate = new_crate(name=name, description=f"Provenance of the {name} workflow execution.", profiles=profiles)
    if workflow_file:
        crate.metadata["conformsTo"] = [{"@id": crate.metadata.profile}, {"@id": WORKFLOW_RO_CRATE}]
    for entity in entities.values():
        _add_entity(crate, entity)

    # The authors of the steps (provenance_author property) are the authors of the workflow crate
    authors = [{"@id": i} for i in dict.fromkeys(ref["@id"] for a in step_actions for ref in as_list(a.get("agent")))]
    workflow = _add_workflow(crate, workflow_file, name, output_dir)
    if license:
        workflow["license"] = _add_license(crate, license)
    steps = []
    control_actions = []
    for position, action in enumerate(step_actions):
        step = crate.add(ContextEntity(crate, f"#step-{position}", properties={
            "@type": "HowToStep",
            # Step name of the workflow configuration file, or the building block name
            "name": action.get("alternateName") or action["name"].removeprefix("Run of "),
            "position": str(position),
            "workExample": action["instrument"],
        }))
        steps.append(step)
        control_actions.append(crate.add(ContextEntity(crate, f"#control-{position}", properties={
            "@type": "ControlAction",
            "name": f"Orchestrate {step['name']}",
            "instrument": {"@id": step.id},
            "object": {"@id": action["@id"]},
        })))
    workflow["step"] = single(steps)
    workflow["hasPart"] = single([{"@id": i} for i in dict.fromkeys(a["instrument"]["@id"] for a in step_actions)])

    inputs, outputs = _workflow_files(step_actions)
    _add_formal_parameters(crate, workflow, inputs, outputs)
    if authors:
        workflow["creator"] = single(authors)
    properties: dict[str, Any] = {
        "@type": "CreateAction",
        "name": f"Run of {name}",
        "description": _run_description(name, step_actions),
        "actionStatus": FAILED if any(a.get("actionStatus") == FAILED for a in step_actions) else COMPLETED,
    }
    start_times = [a["startTime"] for a in step_actions if a.get("startTime")]
    end_times = [a["endTime"] for a in step_actions if a.get("endTime")]
    if start_times:
        properties["startTime"] = min(start_times, key=parse_time)
    if end_times:
        properties["endTime"] = max(end_times, key=parse_time)
    if authors:
        properties["agent"] = crate.root_dataset["author"] = single(authors)
    workflow_action = crate.add_action(workflow, identifier="#workflow-run", object=single(inputs), result=single(outputs), properties=properties)
    crate.root_dataset["mentions"] = [{"@id": workflow_action.id}] + [{"@id": a["@id"]} for a in step_actions]

    engine = crate.add(ContextEntity(crate, "https://github.com/bioexcel/biobb_common", properties={
        "@type": "SoftwareApplication",
        "name": "biobb_common",
        **software_version(__version__),
        "url": "https://github.com/bioexcel/biobb_common",
    }))
    crate.add(ContextEntity(crate, "#orchestrate", properties={
        "@type": "OrganizeAction",
        "name": f"Orchestration of {name}",
        "instrument": {"@id": engine.id},
        "object": single([{"@id": c.id} for c in control_actions]),
        "result": {"@id": workflow_action.id},
    }))

    if is_generated(output_dir / README):
        crate.add_file(dest_path=README, properties={"name": "README", "about": {"@id": "./"}, "encodingFormat": "text/markdown"})
    crate.metadata.write(output_dir)
    if is_generated(output_dir / README):
        write_readme(output_dir)
    if is_generated(output_dir / PREVIEW):
        write_preview(output_dir)
    return output_dir / crate.metadata.id


@contextmanager
def workflow_provenance(path: Union[str, Path] = ".", name: Optional[str] = None,
                        workflow_file: Optional[Union[str, Path]] = None, license: Optional[str] = None) -> Iterator[None]:
    """Enable the provenance of all the building blocks executed inside the
    context and merge their RO-Crates into a workflow RO-Crate on exit.

    Only the blocks executed by the same thread (or asyncio task) are collected.
    To collect blocks executed in other threads, run them in a copy of the
    context, ie: ``executor.submit(contextvars.copy_context().run, block, ...)``.
    Nested contexts write their own workflow crate, and the blocks are also
    collected by the outer contexts.

    Examples:
        This is a use example of how to record the provenance of a workflow::

            from biobb_common.provenance import workflow_provenance
            with workflow_provenance(path="wf_output"):
                pdb2gmx(...)
                editconf(...)

    Args:
        path (str, Path): (".") Directory where the workflow ro-crate-metadata.json will be written.
        name (str): (None) Name of the workflow, by default the workflow file name.
        workflow_file (str, Path): (None) Python script of the workflow, by default the script being executed
            (none in notebooks or when the code is read from the standard input).
        license (str): (None) License of the workflow script: SPDX identifier (ie: "MIT") or URL.
            By default the provenance_license global property, if set.
    """
    if workflow_file is None:
        workflow_file = getattr(sys.modules.get("__main__"), "__file__", None)
        # Not a script file, ie: "<stdin>" with python - < workflow.py: as a notebook, without workflow file
        if workflow_file and not Path(workflow_file).is_file():
            workflow_file = None
    # Block crates next to the workflow crate, unless the blocks set provenance_path
    with tracker.collect(Path(path) / "provenance") as block_crates:
        try:
            yield
        finally:
            if block_crates:
                merge_block_crates(block_crates, path, workflow_file=workflow_file, name=name,
                                   license=license or biobb_global_properties.get("provenance_license"))


def _crate_start(block_crate: Union[str, Path]) -> str:
    """Return the start time with microseconds in the name of a block crate directory
    (<step>_<ClassName>_<YYYYmmdd-HHMMSS-ffffff>), or "" if it has none."""
    block_crate = Path(block_crate)
    directory = block_crate if block_crate.is_dir() else block_crate.parent
    match = re.search(r"_(\d{8}-\d{6}-\d{6})$", directory.name)
    return match.group(1) if match else ""


def _read_graph(block_crate: Union[str, Path]) -> list[dict]:
    block_crate = Path(block_crate)
    if block_crate.is_dir():
        block_crate = block_crate / "ro-crate-metadata.json"
    return json.loads(block_crate.read_text())["@graph"]


def _run_description(name: str, step_actions: list[dict]) -> str:
    """Description of the workflow run, explaining the times of the steps skipped by the restart property."""
    description = f"Execution of the {name} workflow with {len(step_actions)} building blocks."
    skipped = sum(map(is_restart_skipped, step_actions))
    if skipped and skipped == len(step_actions):
        return (f"{RESTART_SKIPPED} (restart-only run): all the {skipped} building blocks of the {name} workflow were skipped, "
                "their outputs come from previous executions that were not recorded. The start time is unknown and the end time "
                "is the last modification of the outputs, the duration of the original execution is not recorded.")
    if skipped:
        return (f"{description} {skipped} of them were skipped by the restart property: their outputs come from previous "
                "executions that were not recorded, so their duration is not included in the start and end times.")
    return description


def _uri(path: str) -> str:
    """Return the file URI of an absolute path of this or another machine, without trailing slash."""
    return Path(path).as_uri().rstrip("/") if Path(path).is_absolute() else Path(path).resolve().as_uri().rstrip("/")


def _replace_ids(value: Any, mapping: dict[str, str], prefix: bool = False) -> Any:
    """Replace the @id of **value** (and nested references) found in **mapping**. With
    **prefix**, the keys are file URI prefixes: file:///a/b replaces file:///a/b and file:///a/b/c,
    only if the new file exists in this machine (ie: files not copied back from a cluster keep their id)."""
    if not mapping:
        return value
    if isinstance(value, list):
        return [_replace_ids(v, mapping, prefix) for v in value]
    if not isinstance(value, dict):
        return value
    value = {k: _replace_ids(v, mapping, prefix) for k, v in value.items()}
    entity_id = value.get("@id")
    if isinstance(entity_id, str):
        if not prefix:
            value["@id"] = mapping.get(entity_id, entity_id)
        else:
            # Longest prefix first, so nested paths can be mapped to other places
            for old in sorted(mapping, key=len, reverse=True):
                if entity_id == old or entity_id.startswith(old + "/"):
                    new_id = mapping[old] + entity_id[len(old):]
                    if Path(unquote(urlsplit(new_id).path)).exists():
                        value["@id"] = new_id
                    break
    return value


def _link_by_checksum(entities: dict[str, dict], order: Callable[[dict], Any] = action_time) -> dict[str, dict]:
    """Link the inputs that no step produced with the output of a previous step with the
    same sha256 (and size), ie: a file copied to an HPC cluster or back. The id of the output is kept.
    The steps are sorted in execution order with the **order** key."""
    actions = sorted((e for e in entities.values() if e["@type"] == "CreateAction"), key=order)
    produced = {ref["@id"] for a in actions for ref in as_list(a.get("result"))}
    # (sha256, size) -> output id, of the steps executed before
    outputs: dict[tuple, str] = {}
    mapping: dict[str, str] = {}
    for action in actions:
        for ref in as_list(action.get("object")):
            entity = entities.get(ref["@id"], {})
            key = (entity.get("sha256"), entity.get("contentSize"))
            if ref["@id"] not in produced and key[0] and key[1] != "0" and key in outputs and outputs[key] != ref["@id"]:
                mapping[ref["@id"]] = outputs[key]
        for ref in as_list(action.get("result")):
            entity = entities.get(ref["@id"], {})
            if entity.get("sha256"):
                outputs[(entity["sha256"], entity.get("contentSize"))] = ref["@id"]
    linked: dict[str, dict] = {}
    for entity_id, entity in entities.items():
        if entity_id not in mapping:
            linked[entity_id] = _replace_ids(entity, mapping)
    return linked


def _relativize(value: Any, output_dir: Path) -> Any:
    """Replace the file URIs inside **output_dir** by paths relative to it, in all the @id of **value**."""
    if isinstance(value, list):
        return [_relativize(v, output_dir) for v in value]
    if not isinstance(value, dict):
        return value
    value = {k: _relativize(v, output_dir) for k, v in value.items()}
    prefix = output_dir.as_uri() + "/"
    if isinstance(value.get("@id"), str) and value["@id"].startswith(prefix):
        value["@id"] = value["@id"][len(prefix):]
    return value


def _add_entity(crate: ROCrate, entity: dict) -> None:
    entity = dict(entity)
    entity_id = entity["@id"]
    if entity["@type"] in ("File", "Dataset"):
        add = crate.add_file if entity["@type"] == "File" else crate.add_dataset
        properties = {k: v for k, v in entity.items() if k not in ("@id", "@type")}
        if entity_id.startswith("file:"):
            add(entity_id, properties=properties)
        else:
            add(dest_path=entity_id, properties=properties)
    else:
        crate.add_jsonld(entity)


def _add_workflow(crate: ROCrate, workflow_file: Optional[Union[str, Path]], name: str, output_dir: Path):
    python = crate.add(ContextEntity(crate, "https://w3id.org/workflowhub/workflow-ro-crate#python", properties={
        "@type": "ComputerLanguage",
        "name": "Python",
        "identifier": {"@id": "https://www.python.org/"},
        "url": {"@id": "https://www.python.org/"},
        "version": platform.python_version(),
    }))
    bioschemas = crate.add(ContextEntity(crate, COMPUTATIONAL_WORKFLOW, properties={
        "@type": "CreativeWork",
        "name": "Bioschemas ComputationalWorkflow profile",
        "version": "1.0-RELEASE",
    }))
    properties = {
        "@type": ["File", "SoftwareSourceCode", "ComputationalWorkflow", "HowTo"],
        "conformsTo": {"@id": bioschemas.id},
        "name": name,
        "programmingLanguage": {"@id": python.id},
        "encodingFormat": "text/x-python",
        "sdPublisher": {"@id": PUBLISHER},
    }
    if workflow_file is None:
        # ie: Jupyter notebook, there is no file to add to the crate: not the mainEntity and not Bioschemas compliant
        properties["@type"] = ["ComputationalWorkflow", "HowTo"]
        for key in ("conformsTo", "encodingFormat"):
            del properties[key]
        return crate.add(ContextEntity(crate, "#workflow", properties=properties))
    path = Path(workflow_file).resolve()
    properties.update(_script_metadata(path))
    if not path.is_relative_to(output_dir):
        shutil.copy2(path, output_dir / path.name)
        path = output_dir / path.name
    workflow = crate.add_file(dest_path=path.relative_to(output_dir), properties=properties)
    crate.mainEntity = workflow
    return workflow


def _add_license(crate: ROCrate, license: str):
    """Add a license given as SPDX identifier (ie: "MIT") or URL."""
    if license.startswith(("http://", "https://")):
        return crate.add(ContextEntity(crate, license, properties={"@type": "CreativeWork", "name": license}))
    return crate.add(ContextEntity(crate, f"https://spdx.org/licenses/{license}", properties={
        "@type": "CreativeWork",
        "name": license,
        "identifier": license,
    }))


def _script_metadata(path: Path) -> dict[str, str]:
    """Return the version, url and creation date of a workflow script.

    In a git repository with a remote, the version is the commit and the url
    points to the script at that commit. Otherwise (or if the script has
    uncommitted changes) the version is the sha256 of the script and the url
    its original file URI.
    """
    metadata = {
        "version": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
        "url": path.as_uri(),
        "dateCreated": iso(datetime.fromtimestamp(path.stat().st_mtime).astimezone()),
    }
    commit = _git(path.parent, "rev-parse", "HEAD")
    if commit and _git(path.parent, "ls-files", "--error-unmatch", path.name) is not None and not _git(path.parent, "status", "--porcelain", path.name):
        metadata["version"] = commit
        remote = _git(path.parent, "config", "--get", "remote.origin.url")
        root = _git(path.parent, "rev-parse", "--show-toplevel")
        if remote and root:
            metadata["url"] = f"{_web_url(remote)}/blob/{commit}/{path.relative_to(Path(root).resolve()).as_posix()}"
    return metadata


def _git(directory: Path, *args: str) -> Optional[str]:
    """Return the output of a git command, None if it fails or git is not installed."""
    try:
        return subprocess.run(["git", "-C", str(directory), *args], capture_output=True, text=True, timeout=30, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def _web_url(remote: str) -> str:
    """Return the web URL of a git remote without credentials,
    ie: git@github.com:bioexcel/biobb_wf.git -> https://github.com/bioexcel/biobb_wf"""
    match = re.match(r"^[\w.-]+@([\w.-]+):(.+)$", remote)
    if match:
        remote = f"https://{match.group(1)}/{match.group(2)}"
    parts = urlsplit(remote)
    netloc = parts.hostname or ""
    if parts.port and parts.scheme in ("http", "https"):
        netloc += f":{parts.port}"
    return urlunsplit(("https", netloc, parts.path.rstrip("/").removesuffix(".git"), "", ""))


def _add_formal_parameters(crate: ROCrate, workflow, inputs: list[dict], outputs: list[dict]) -> None:
    """Describe the workflow inputs and outputs as FormalParameters (Bioschemas), each
    file is an exampleOfWork of its parameter."""
    profile = crate.add(ContextEntity(crate, FORMAL_PARAMETER, properties={
        "@type": "CreativeWork",
        "name": "Bioschemas FormalParameter profile",
        "version": "1.0-RELEASE",
    }))
    for key, refs in (("input", inputs), ("output", outputs)):
        parameters = []
        for ref in refs:
            file = crate.get(ref["@id"])
            if file is None:
                continue
            parameter = crate.add(ContextEntity(crate, f"#{key}-{len(parameters)}", properties={
                "@type": "FormalParameter",
                "conformsTo": {"@id": profile.id},
                "name": file.get("name", ref["@id"]),
                "additionalType": "Dataset" if "Dataset" in as_list(file.type) else "File",
                **({"encodingFormat": file.properties()["encodingFormat"]} if "encodingFormat" in file.properties() else {}),
            }))
            file["exampleOfWork"] = {"@id": parameter.id}
            parameters.append({"@id": parameter.id})
        if parameters:
            workflow[key] = single(parameters)


def _workflow_files(step_actions: list[dict]) -> tuple[list[dict], list[dict]]:
    """Return the workflow inputs (consumed but not produced by any step) and
    outputs (produced but not consumed by any step) as @id references."""
    def ids(key: str) -> list[str]:
        return [ref["@id"] for action in step_actions for ref in as_list(action.get(key)) if not ref["@id"].startswith("#")]
    consumed, produced = ids("object"), ids("result")
    inputs = [i for i in dict.fromkeys(consumed) if i not in produced]
    outputs = [o for o in dict.fromkeys(produced) if o not in consumed]
    return [{"@id": i} for i in inputs], [{"@id": o} for o in outputs]
