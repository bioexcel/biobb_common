"""Module containing the functions to build the workflow RO-Crate from the building block RO-Crates."""
import hashlib
import json
import platform
import re
import shutil
import subprocess
import sys
import zipfile
import zlib
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path, PurePosixPath
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
# Fragment of the ids of the versions of a file written several times: <file URI>#version-<n>
VERSION = "#version-"
# Tool of the steps inferred from the content of zip files: extractions and zips done by the workflow script
ZIP_TOOL = "#workflow-script-zip"


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
    with the same sha256. Files that the workflow script extracted from the zip of a
    step, or zipped for the next one, are linked by steps inferred from the content of
    the zip members. Without **workflow_file** (ie: Jupyter notebooks) the crate only
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
    # Execution order of the block crates (directory name), to order the steps with equal times
    crate_ranks = {index: rank for rank, index in enumerate(sorted(range(len(block_crates)), key=lambda i: _crate_start(block_crates[i])))}
    action_ranks: dict[str, int] = {}
    crate_graphs: list[list[dict]] = []
    for index, block_crate in enumerate(block_crates):
        graph = []
        for entity in _read_graph(block_crate):
            entity = _replace_ids(entity, uri_map, prefix=True)
            if entity["@id"] in SKIPPED_IDS:
                continue
            if entity["@type"] == "CreateAction":
                action_ranks[entity["@id"]] = crate_ranks[index]
            graph.append(entity)
        crate_graphs.append(graph)

    def order(action: dict) -> tuple:
        return action_time(action), action_ranks.get(action["@id"], -1)

    entities = _merge_inputs(_link_by_checksum(_version_files(crate_graphs, order), order))
    entities = _final_versions(_link_through_zips(entities, order, action_ranks))
    relative: dict[str, dict] = {}
    for entity in entities.values():
        entity = _relativize(entity, output_dir)
        if entity["@id"] not in SKIPPED_IDS:
            relative.setdefault(entity["@id"], {}).update(entity)
    entities = relative
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
    inferred = [a for a in step_actions if a["instrument"]["@id"] == ZIP_TOOL]
    description = _run_description(name, [a for a in step_actions if a["instrument"]["@id"] != ZIP_TOOL])
    if inferred:
        description += (f" {len(inferred)} more steps, the extraction and creation of zip files by the workflow script, "
                        "are inferred from the content of the files.")
    properties: dict[str, Any] = {
        "@type": "CreateAction",
        "name": f"Run of {name}",
        "description": description,
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


def _version_files(crate_graphs: list[list[dict]], order: Callable[[dict], Any]) -> dict[str, dict]:
    """Merge the entities of the block crates, with one entity per version of each file.

    A path written by several steps (ie: a file rewritten in a loop, or renamed and written
    again) holds a different content after each of them. Following the execution order, each
    step that writes a path creates a new version, and the steps that read it use the version
    written last before them. Each read of a path that no previous step wrote, or whose checksum
    (or size, without checksums) differs from the version written last (modified outside the
    steps, ie: renamed over), is a new version not produced by any step: _link_by_checksum links
    it to the output it comes from and _merge_inputs merges the ones of the same content left
    (ie: a workflow input read by several steps). Versions get the provisional id
    <path>#version-<n>, see _final_versions.
    """
    versions: dict[str, list[dict]] = {}
    current: dict[str, dict] = {}
    produced: set[str] = set()
    entities: dict[str, dict] = {}

    def new_version(path: str, entity: dict) -> dict:
        version = {**entity, "@id": f"{path}{VERSION}{len(versions.setdefault(path, [])) + 1}"}
        versions[path].append(version)
        entities[version["@id"]] = version
        return version

    steps = sorted(((e, graph) for graph in crate_graphs for e in graph if e["@type"] == "CreateAction"), key=lambda step: order(step[0]))
    seen: set[str] = set()
    for action, graph in steps:
        # The same crate twice (ie: reused by the restart property) is the same execution
        if action["@id"] in seen:
            continue
        seen.add(action["@id"])
        files = {e["@id"]: e for e in graph if e["@type"] in ("File", "Dataset")}
        inputs: dict[str, str] = {}
        for ref in as_list(action.get("object")):
            if ref["@id"] in files:
                version = current.get(ref["@id"])
                # A file with the same content may have been renamed over it (ie: tmp.pdb of a pipeline)
                if version is None or version["@id"] not in produced or not _same_content(version, files[ref["@id"]]):
                    version = current[ref["@id"]] = new_version(ref["@id"], files[ref["@id"]])
                inputs[ref["@id"]] = version["@id"]
        outputs: dict[str, str] = {}
        for ref in as_list(action.get("result")):
            if ref["@id"] in files:
                version = current[ref["@id"]] = new_version(ref["@id"], files[ref["@id"]])
                produced.add(version["@id"])
                outputs[ref["@id"]] = version["@id"]
        # Other references to the files of the crate (ie: subjectOf of a parameter file) are to its inputs
        references = {**outputs, **inputs}
        for entity in graph:
            if entity["@id"] in references:
                version = entities[inputs[entity["@id"]]] if entity["@id"] in inputs else None
                if version is not None:
                    # The input already read by the previous steps, completed with what this step recorded
                    version.update({k: v for k, v in entity.items() if k != "@id" and k not in version})
                continue
            entity = {k: _replace_ids(v, references) for k, v in entity.items() if k not in ("object", "result") or entity is not action}
            if entity["@id"] == action["@id"]:
                for key, mapping in (("object", inputs), ("result", outputs)):
                    if key in action:
                        entity[key] = _replace_ids(action[key], mapping)
            entities.setdefault(entity["@id"], {}).update(entity)
    return entities


def _same_content(version: dict, entity: dict) -> bool:
    """Return False if a file entity has another sha256 (or size, without checksums) than a version of the file."""
    if version.get("sha256") and entity.get("sha256"):
        return (version["sha256"], version.get("contentSize")) == (entity["sha256"], entity.get("contentSize"))
    if "contentSize" in version and "contentSize" in entity:
        return version["contentSize"] == entity["contentSize"]
    return True


def _merge_inputs(entities: dict[str, dict]) -> dict[str, dict]:
    """Merge the versions of a path that no step produced and have the same content (sha256 and
    size), ie: a workflow input read by several steps, that _version_files kept apart so that
    _link_by_checksum could link each read to the output it comes from. The first one is kept."""
    produced = {ref["@id"] for e in entities.values() if e["@type"] == "CreateAction" for ref in as_list(e.get("result"))}
    first: dict[tuple, str] = {}
    mapping: dict[str, str] = {}
    # In creation order, which is the execution order
    for entity_id, entity in entities.items():
        path, _, number = entity_id.rpartition(VERSION)
        if not path or not number.isdigit() or entity_id in produced:
            continue
        key = (path, entity.get("sha256"), entity.get("contentSize"))
        if key in first:
            mapping[entity_id] = first[key]
        else:
            first[key] = entity_id
    return {i: _replace_ids(e, mapping) for i, e in entities.items() if i not in mapping}


def _link_through_zips(entities: dict[str, dict], order: Callable[[dict], Any], ranks: dict[str, Any]) -> dict[str, dict]:
    """Add the steps of the workflow script that extract files from a zip, or make a zip, between building blocks.

    An input that no step produced, with the content (sha256 and size, or CRC-32 and size
    without checksums) and the name of a member of a zip written by a previous step, was
    extracted from it (ie: with zipfile): an extraction step links the zip to the files. A zip
    input that no step produced, whose members have the content and name of outputs of previous
    steps, was made from them: a step links those outputs to the zip. Member names may have a
    prefix (ie: file_1_<name> of file_utils.zip_list). Only the zips still on disk are read. These
    steps are inferred, not recorded: their time is the end of the last step they depend on, and
    **ranks** (order of the steps with equal times) gets theirs, right after that step.
    """
    actions = sorted((e for e in entities.values() if e["@type"] == "CreateAction"), key=order)
    producer = {ref["@id"]: i for i, a in enumerate(actions) for ref in as_list(a.get("result"))}
    first_use: dict[str, int] = {}
    for i, action in enumerate(actions):
        for ref in as_list(action.get("object")):
            first_use.setdefault(ref["@id"], i)
    last_version: dict[str, int] = {}
    for entity_id in entities:
        path, _, number = entity_id.rpartition(VERSION)
        if path and number.isdigit():
            last_version[path] = max(last_version.get(path, 0), int(number))
    members: dict[Path, list[zipfile.ZipInfo]] = {}
    digests: dict[tuple[Path, str], str] = {}

    def zip_members(entity_id: str) -> list[zipfile.ZipInfo]:
        """Members of a zip file with the content recorded in its entity, empty if it is not."""
        path, _, number = entity_id.rpartition(VERSION)
        file = _file_path(entity_id)
        if file is None or file.suffix.lower() != ".zip" or (number.isdigit() and int(number) != last_version.get(path)) \
                or not _on_disk(path or entity_id, entities[entity_id]):
            return []
        if file not in members:
            try:
                with zipfile.ZipFile(file) as archive:
                    members[file] = [m for m in archive.infolist() if not m.is_dir() and m.file_size]
            except (OSError, zipfile.BadZipFile):
                members[file] = []
        return members[file]

    def is_member(file_id: str, archive: Path, member: zipfile.ZipInfo, same_name: bool) -> bool:
        """Return True if a file entity has the content (and with **same_name**, the name) of a zip member.
        Without sha256 the name is always required, the CRC-32 is a weaker check."""
        entity, file = entities[file_id], _file_path(file_id)
        name = PurePosixPath(member.filename).name
        if file is None or str(member.file_size) != str(entity.get("contentSize")):
            return False
        if (same_name or not entity.get("sha256")) and not (name == file.name or name.endswith("_" + file.name)):
            return False
        if entity.get("sha256"):
            if (archive, member.filename) not in digests:
                digest = hashlib.sha256()
                with zipfile.ZipFile(archive) as zip_file, zip_file.open(member) as content:
                    for chunk in iter(lambda: content.read(1024 * 1024), b""):
                        digest.update(chunk)
                digests[archive, member.filename] = digest.hexdigest()
            return digests[archive, member.filename] == entity["sha256"]
        return file.is_file() and file.stat().st_size == member.file_size and _crc32(file) == member.CRC

    files = [i for i, e in entities.items() if e["@type"] == "File"]
    produced_files = sorted((i for i in files if i in producer), key=producer.__getitem__)
    produced_zips = [i for i in produced_files if zip_members(i)]
    new_steps: list[tuple[str, str, list[str], list[str], int]] = []
    # Extractions: inputs that are members of a zip written before they are read (latest zip first,
    # a member with the same name first)
    extracted: dict[str, list[str]] = {}
    for file_id in files:
        if file_id in producer or file_id not in first_use:
            continue
        zip_id = next((z for same_name in (True, False) for z in reversed(produced_zips) if producer[z] < first_use[file_id]
                       and any(is_member(file_id, _file_path(z), m, same_name) for m in zip_members(z))), None)
        if zip_id:
            extracted.setdefault(zip_id, []).append(file_id)
    for zip_id, file_ids in extracted.items():
        new_steps.append(("extract", zip_id, [zip_id], file_ids, producer[zip_id]))
    # Zips made by the script: each member is the latest output with its content (and name, first) written before the zip is read
    linked = {i for ids in extracted.values() for i in ids}
    for zip_id in files:
        if zip_id in producer or zip_id in linked or zip_id not in first_use or not zip_members(zip_id):
            continue
        archive = _file_path(zip_id)
        sources: list[str] = []
        for member in zip_members(zip_id):
            source = next((f for same_name in (True, False) for f in reversed(produced_files) if producer[f] < first_use[zip_id]
                           and f not in sources and is_member(f, archive, member, same_name)), None)
            if source:
                sources.append(source)
        if sources:
            new_steps.append(("zip", zip_id, sources, [zip_id], max(producer[i] for i in sources)))
    if not new_steps:
        return entities

    entities[ZIP_TOOL] = {
        "@id": ZIP_TOOL,
        "@type": "SoftwareApplication",
        "name": "Workflow script (zip files)",
        "description": "Extraction and creation of zip files by the workflow script, outside the building blocks (ie: with the Python zipfile "
                       "module). Its steps are inferred from the content and names of the files and the zip members, they were not recorded.",
    }
    for number, (kind, zip_id, objects, results, after) in enumerate(new_steps, start=1):
        previous = actions[after]
        zip_name = entities[zip_id].get("name") or _file_path(zip_id).name
        if kind == "extract":
            name = f"Extraction of {zip_name}"
            description = (f"{len(results)} files extracted from {zip_name} by the workflow script, outside the building blocks: "
                           "inferred from their content and names, the members of the zip. The time is the end of the step that wrote the zip.")
        else:
            name = f"Creation of {zip_name}"
            description = (f"{zip_name} made by the workflow script from {len(objects)} outputs of previous steps, outside the building blocks: "
                           "inferred from the content and names of its members. The time is the end of the last step that wrote them.")
        action_id = f"#workflow-script-{kind}-{number}"
        time = previous.get("endTime") or previous.get("startTime")
        entities[action_id] = {
            "@id": action_id,
            "@type": "CreateAction",
            "name": name,
            # Name of the step in the graphs (the building block steps have the name of the configuration step)
            "alternateName": name,
            "description": description,
            "instrument": {"@id": ZIP_TOOL},
            "object": single([{"@id": i} for i in objects]),
            "result": single([{"@id": i} for i in results]),
            "actionStatus": COMPLETED,
            **({"startTime": time, "endTime": time} if time else {}),
        }
        ranks[action_id] = ranks.get(previous["@id"], -1) + 0.5
    return entities


def _file_path(entity_id: str) -> Optional[Path]:
    """Return the local path of a file URI (without the version fragment), None for other ids."""
    uri = entity_id.rpartition(VERSION)[0] or entity_id
    return Path(unquote(urlsplit(uri).path)) if uri.startswith("file:") else None


def _crc32(path: Path) -> int:
    crc = 0
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            crc = zlib.crc32(chunk, crc)
    return crc


def _final_versions(entities: dict[str, dict]) -> dict[str, dict]:
    """Replace the provisional ids of the file versions (<path>#version-<n>) by their final ids.

    A path with a single version keeps its id. Of the paths written several times, the last
    version keeps the id of the path if the file is still there (with the same size), the
    others keep the fragment, renumbered in execution order (versions linked by checksum to
    the output of another step are no longer there), and all of them get their version number.
    """
    versions: dict[str, list[str]] = {}
    for entity_id in entities:
        path, _, number = entity_id.rpartition(VERSION)
        if path and number.isdigit():
            versions.setdefault(path, []).append(entity_id)
    mapping: dict[str, str] = {}
    for path, ids in versions.items():
        ids.sort(key=lambda i: int(i.rpartition(VERSION)[2]))
        if len(ids) == 1:
            mapping[ids[0]] = path
            continue
        for number, entity_id in enumerate(ids, start=1):
            mapping[entity_id] = f"{path}{VERSION}{number}"
            entity = entities[entity_id]
            entity["version"] = str(number)
            entity["description"] = (f"Version {number} of {len(ids)} of {entity.get('name', path)}: the path was written again later, "
                                     "this content is no longer there.")
        if _on_disk(path, entities[ids[-1]]):
            mapping[ids[-1]] = path
            del entities[ids[-1]]["description"]
        else:
            entities[ids[-1]]["description"] = (f"Version {len(ids)} of {len(ids)} of {entities[ids[-1]].get('name', path)}: "
                                                "not at this path when the provenance was merged (ie: renamed, removed or on another machine).")
    return {mapping.get(i, i): _replace_ids(e, mapping) for i, e in entities.items()}


def _on_disk(file_id: str, entity: dict) -> bool:
    """Return True if a file (or directory) URI exists in this machine with the size recorded in **entity**."""
    if not file_id.startswith("file:"):
        return False
    path = Path(unquote(urlsplit(file_id).path))
    if not path.exists():
        return False
    return "Dataset" in as_list(entity.get("@type")) or "contentSize" not in entity or str(path.stat().st_size) == str(entity["contentSize"])


def _relativize(value: Any, output_dir: Path) -> Any:
    """Replace the file URIs inside **output_dir** by paths relative to it, in all the @id of **value**.
    Only the files that exist: the others (ie: renamed or removed, earlier versions of a file
    written several times) keep their absolute URI, they are not part of the crate payload."""
    if isinstance(value, list):
        return [_relativize(v, output_dir) for v in value]
    if not isinstance(value, dict):
        return value
    value = {k: _relativize(v, output_dir) for k, v in value.items()}
    prefix = output_dir.as_uri() + "/"
    entity_id = value.get("@id")
    if isinstance(entity_id, str) and entity_id.startswith(prefix) and not urlsplit(entity_id).fragment \
            and Path(unquote(urlsplit(entity_id).path)).exists():
        value["@id"] = entity_id[len(prefix):]
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
            # Relative ids are URI encoded (ie: A%3AGly4Lys for A:Gly4Lys) and rocrate encodes dest_path again
            add(dest_path=unquote(entity_id), properties=properties)
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
