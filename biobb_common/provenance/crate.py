"""Module containing the functions to write the provenance records as RO-Crates."""
import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

from rocrate.model.contextentity import ContextEntity
from rocrate.rocrate import ROCrate

from biobb_common.provenance.parameters import ParameterSet
from biobb_common.provenance.record import BlockRecord, FileRecord

RO_CRATE_VERSION = "1.1"
PROCESS_RUN_CRATE = "https://w3id.org/ro/wfrun/process/0.5"
WORKFLOW_RUN_TERMS = "https://w3id.org/ro/terms/workflow-run"
EDAM_URI = "http://edamontology.org/"
LICENSE = "https://www.apache.org/licenses/LICENSE-2.0"
PUBLISHER = "https://bioexcel.eu/"
COMPLETED = "http://schema.org/CompletedActionStatus"
FAILED = "http://schema.org/FailedActionStatus"
# Terms not covered by schema.org or the workflow-run vocabulary
BIOBB_TERMS = "https://biobb-common.readthedocs.io/en/latest/provenance.html#"
EXTRA_TERMS = {"executionEnvironment": BIOBB_TERMS + "executionEnvironment"}
# Start of the description of the executions skipped by the restart property
RESTART_SKIPPED = "Skipped by the restart property"


def new_crate(name: str, description: str, profiles: dict[str, tuple[str, str]]) -> ROCrate:
    """Return an empty RO-Crate with the root metadata common to all the biobb crates.

    Args:
        name (str): Name of the crate.
        description (str): Description of the crate.
        profiles (dict): {profile URI: (profile name, profile version)} the crate conforms to.
    """
    crate = ROCrate(version=RO_CRATE_VERSION)
    crate.metadata.extra_contexts.append(WORKFLOW_RUN_TERMS)
    crate.metadata.extra_terms.update(EXTRA_TERMS)
    crate.root_dataset["conformsTo"] = single([
        crate.add(ContextEntity(crate, uri, properties={"@type": ["CreativeWork", "Profile"], "name": profile, "version": version}))
        for uri, (profile, version) in profiles.items()
    ])
    crate.root_dataset["name"] = name
    crate.root_dataset["description"] = description
    crate.root_dataset["license"] = crate.add(ContextEntity(crate, LICENSE, properties={
        "@type": "CreativeWork",
        "name": "Apache License 2.0",
        "identifier": "Apache-2.0",
    }))
    crate.root_dataset["publisher"] = crate.add(ContextEntity(crate, PUBLISHER, properties={
        "@type": "Organization",
        "name": "BioExcel Centre of Excellence",
        "url": PUBLISHER,
    }))
    return crate


def add_author(crate: ROCrate, author: dict[str, str]):
    """Add the author of the crate, a Person identified by its ORCID if available.

    Args:
        crate (ROCrate): Crate where the author is added.
        author (dict): {"name": str, "orcid": str, "affiliation": str, "affiliation_url": str}, only name is required.
    """
    properties: dict[str, Any] = {"@type": "Person", "name": author["name"]}
    if author.get("affiliation"):
        affiliation = {"@type": "Organization", "name": author["affiliation"]}
        if author.get("affiliation_url"):
            affiliation["url"] = author["affiliation_url"]
        properties["affiliation"] = crate.add(ContextEntity(crate, "#" + _slug(author["affiliation"]), properties=affiliation))
    identifier = author.get("orcid") or "#" + _slug(author["name"])
    return crate.add(ContextEntity(crate, identifier, properties=properties))


def write_block_crate(record: BlockRecord, crate_dir: Union[str, Path]) -> Path:
    """Write the RO-Crate (Process Run Crate profile) of a building block execution.

    Only the ro-crate-metadata.json file is written, the input and output files
    are referenced by their absolute file URI and never copied.

    Args:
        record (BlockRecord): Provenance record of the execution.
        crate_dir (str, Path): Directory where the ro-crate-metadata.json will be written.

    Returns:
        Path: Path to the written ro-crate-metadata.json file.
    """
    crate = new_crate(
        name=f"{record.package} {record.class_name} execution",
        description=f"Provenance of the {record.package} {record.class_name} building block execution.",
        profiles={PROCESS_RUN_CRATE: ("Process Run Crate", "0.5")},
    )
    crate.root_dataset["datePublished"] = iso(datetime.now().astimezone())

    instrument = crate.add(ContextEntity(crate, block_id(record.module, record.class_name), properties={
        "@type": "SoftwareApplication",
        "name": f"{record.package} {record.class_name}",
        **software_version(record.package_version),
        "url": f"https://github.com/bioexcel/{record.package}",
    }))
    if record.wrapped_software:
        instrument["softwareRequirements"] = _add_wrapped_software(crate, record)

    action_id = f"#{uuid.uuid4()}"
    parameters = [
        crate.add(ContextEntity(crate, f"{action_id}-{name}", properties={
            "@type": "PropertyValue",
            "name": name,
            "value": value if isinstance(value, (str, int, float, bool)) else json.dumps(value),
        }))
        for name, value in record.properties.items()
    ] + [_add_parameter_set(crate, action_id, parameter_set) for parameter_set in record.parameters]

    properties: dict[str, Any] = {
        "@type": "CreateAction",
        "name": f"Run of {record.package} {record.class_name}",
        "description": _action_description(record),
        **({"alternateName": record.step} if record.step else {}),
        **({"startTime": iso(record.start_time)} if record.start_time else {}),
        **({"endTime": iso(record.end_time)} if record.end_time else {}),
        "actionStatus": COMPLETED if record.completed else FAILED,
    }
    if record.error:
        properties["error"] = record.error
    if record.container_image:
        container_type = "DockerImage" if record.container_runtime == "docker" else "SIFImage"
        properties["containerImage"] = crate.add(ContextEntity(crate, f"#container-{record.container_image}", properties={
            "@type": "ContainerImage",
            "additionalType": {"@id": f"{WORKFLOW_RUN_TERMS}#{container_type}"},
            **_image_reference(record.container_image),
            **({"sha256": record.container_digest} if record.container_digest else {}),
        }))
    if record.environment:
        properties["executionEnvironment"] = _add_environment(crate, record.environment)

    if record.author:
        properties["agent"] = crate.root_dataset["author"] = add_author(crate, record.author)

    action = crate.add_action(
        instrument,
        identifier=action_id,
        object=single([_add_file(crate, f) for f in record.inputs] + parameters),
        result=single([_add_file(crate, f) for f in record.outputs]),
        properties=properties,
    )
    crate.root_dataset["mentions"] = action

    crate_dir = Path(crate_dir)
    crate_dir.mkdir(parents=True, exist_ok=True)
    crate.metadata.write(crate_dir)
    return crate_dir / crate.metadata.id


def block_id(module: str, class_name: str) -> str:
    """Return the documentation URL of a building block as its id, ie:
    biobb_gromacs.gromacs.pdb2gmx -> https://biobb-gromacs.readthedocs.io/en/latest/gromacs.html#module-gromacs.pdb2gmx"""
    parts = module.split(".")
    if len(parts) != 3:
        return f"#{module}.{class_name}"
    package, subpackage, _ = parts
    return f"https://{package.replace('_', '-')}.readthedocs.io/en/latest/{subpackage}.html#module-{'.'.join(parts[1:])}"


def _add_environment(crate: ROCrate, environment: dict[str, Any]):
    """Add the execution environment: one PropertyValue describing the machine, with its values as
    valueReference. Ids are based on the content, so the steps that ran on the same machine share
    the entity in the workflow crate, and steps on different machines have different entities."""
    values = [
        crate.add(ContextEntity(crate, "#env-" + _slug(f"{name}-{value}"), properties={
            "@type": "PropertyValue",
            "name": name,
            "value": value,
        }))
        for name, value in environment.items()
    ]
    digest = hashlib.sha256(json.dumps(environment, sort_keys=True, default=str).encode()).hexdigest()[:12]
    return crate.add(ContextEntity(crate, f"#environment-{digest}", properties={
        "@type": "PropertyValue",
        "name": "execution environment",
        "value": environment_label(environment),
        "valueReference": single(values),
    }))


def environment_label(environment: dict[str, Any]) -> str:
    """Return a short description of an execution environment, ie: "user@node1 (SLURM cluster mn5, job 123): Linux 6.8, x86_64, 112 CPUs"."""
    host = "@".join(str(environment[k]) for k in ("username", "hostname") if environment.get(k))
    slurm = ", ".join(f"{label} {environment[k]}" for k, label in (("slurm_cluster_name", "SLURM cluster"), ("slurm_job_id", "job")) if environment.get(k))
    machine = ", ".join(str(environment[k]) for k in ("operating_system", "architecture") if environment.get(k))
    if environment.get("cpu_count"):
        machine += f", {environment['cpu_count']} CPUs"
    if environment.get("gpu_model"):
        machine += f", {environment.get('gpu_count', 1)} x {environment['gpu_model']}"
    prefix = " ".join(p for p in (host, f"({slurm})" if slurm else "") if p)
    return f"{prefix}: {machine}" if prefix else machine


def _add_parameter_set(crate: ROCrate, action_id: str, parameter_set: ParameterSet):
    """Add the parameters read from a parameter file: one PropertyValue named as the file,
    with the parameters as valueReference. Input files are linked with subjectOf."""
    group_id = f"{action_id}-{_slug(parameter_set.name)}"
    values = [
        crate.add(ContextEntity(crate, f"{group_id}-{_slug(name)}", properties={"@type": "PropertyValue", "name": name, "value": value}))
        for name, value in parameter_set.values.items()
    ]
    origin = "generated by the building block" if parameter_set.generated else "read from the input file"
    properties: dict[str, Any] = {
        "@type": "PropertyValue",
        "name": parameter_set.name,
        "value": f"{len(values)} parameters",
        "description": f"Parameters of the {parameter_set.file_format} file {parameter_set.name}, {origin}.",
        "valueReference": single(values),
    }
    if parameter_set.path:
        properties["subjectOf"] = {"@id": parameter_set.path.as_uri()}
    return crate.add(ContextEntity(crate, group_id, properties=properties))


def action_environment(action: dict, entities: dict[str, dict]) -> tuple[str, list[dict]]:
    """Return the id of the execution environment of a CreateAction and its values, ("", []) if it has none.
    Crates of previous biobb_common versions link the values directly: their ids joined are the id."""
    refs = as_list(action.get("executionEnvironment"))
    values = [entities.get(r["@id"], {}) for r in refs]
    if len(values) == 1 and "valueReference" in values[0]:
        return refs[0]["@id"], [entities.get(r["@id"], {}) for r in as_list(values[0]["valueReference"])]
    return " ".join(sorted(r["@id"] for r in refs)), values


def is_restart_skipped(action: dict) -> bool:
    """Return True if a CreateAction of a crate was skipped by the restart property."""
    return str(action.get("description", "")).startswith(RESTART_SKIPPED)


def action_time(action: dict) -> datetime:
    """Return the time used to order the CreateActions of a crate: the start time or, for
    executions skipped by the restart property, the end time (last modification of the outputs)."""
    return parse_time(action.get("startTime") or action.get("endTime"))


def parse_time(text: Optional[str]) -> datetime:
    """Return an ISO 8601 time as an aware datetime, so times of machines in different time zones
    can be compared. Unknown or invalid times are the oldest possible time."""
    try:
        time = datetime.fromisoformat(str(text))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    return time if time.tzinfo else time.astimezone()


def _action_description(record: BlockRecord) -> str:
    if record.skipped:
        return (f"{RESTART_SKIPPED}: the outputs come from a previous execution that was not recorded. "
                "Its start time is unknown, the end time is the last modification of the outputs.")
    if record.command_line:
        return f"Command line: {record.command_line}"
    return f"Execution of the {record.class_name} building block."


def software_version(version: Optional[str]) -> dict[str, Optional[str]]:
    """Return the version property of a SoftwareApplication: Process Run Crate 0.5 (RO-Crate 1.1)
    recommends softwareVersion, RO-Crate 1.3 requires version."""
    return {"softwareVersion" if RO_CRATE_VERSION == "1.1" else "version": version}


def single(values: list) -> Any:
    """Return the element of a one element list, RO-Crate prefers single values to singleton arrays."""
    return values[0] if len(values) == 1 else values


def as_list(value: Any) -> list:
    """Return the value of a JSON-LD property as a list."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def iso(time) -> str:
    return time.isoformat(timespec="seconds")


def _image_reference(image: str) -> dict[str, str]:
    """Return the registry, name and tag of a container image reference,
    ie: "docker://quay.io/biocontainers/gromacs:2022.2" -> quay.io, biocontainers/gromacs, 2022.2.
    Local image files (ie: gromacs.sif) only have a name."""
    if Path(image).is_file():
        return {"name": Path(image).name}
    reference = re.sub(r"^\w+://", "", image).split("@", 1)[0]
    name, tag = reference, None
    if ":" in reference.rsplit("/", 1)[-1]:
        name, tag = reference.rsplit(":", 1)
    registry = "docker.io"
    first, _, rest = name.partition("/")
    if rest and ("." in first or ":" in first or first == "localhost"):
        registry, name = first, rest
    return {k: v for k, v in {"registry": registry, "name": name, "tag": tag}.items() if v}


def _add_wrapped_software(crate: ROCrate, record: BlockRecord):
    software = record.wrapped_software
    properties = {
        "@type": "SoftwareApplication",
        "name": software.name,
        **software_version(software.version),
        "license": software.license,
        "url": software.url,
    }
    if not software.version and software.requirement:
        properties["description"] = f"Version not detected, documented requirement: {software.requirement}"
    # Absolute id when the package page is known. The fragment keeps apart the tools of
    # the same package (ie: AmberTools Sander and tLeap) and their versions.
    identifier = (software.url or "") + "#" + _slug(f"{software.name}-{software.version or 'unknown'}")
    return crate.add(ContextEntity(crate, identifier, properties={k: v for k, v in properties.items() if v}))


def _add_file(crate: ROCrate, file_record: FileRecord):
    properties: dict[str, Any] = {"name": file_record.path.name}
    if file_record.edam_format:
        # RO-Crate 1.1: encodingFormat is a MIME type or a reference to a WebSite describing the format
        properties["encodingFormat"] = crate.add(ContextEntity(crate, EDAM_URI + file_record.edam_format, properties={
            "@type": "WebSite",
            "name": f"EDAM {file_record.edam_format}",
        }))
    if file_record.size is not None:
        properties["contentSize"] = str(file_record.size)
    if file_record.sha256:
        properties["sha256"] = file_record.sha256
    if file_record.is_dir:
        return crate.add_dataset(file_record.uri, properties=properties)
    return crate.add_file(file_record.uri, properties=properties)


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9.]+", "-", text).strip("-")
