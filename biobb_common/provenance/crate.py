"""Module containing the functions to write the provenance records as RO-Crates."""
import json
import re
import uuid
from pathlib import Path
from typing import Any, Optional, Union

from rocrate.model.contextentity import ContextEntity
from rocrate.rocrate import ROCrate

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
    crate.root_dataset["datePublished"] = iso(record.end_time)

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
    ]

    properties: dict[str, Any] = {
        "@type": "CreateAction",
        "name": f"Run of {record.package} {record.class_name}",
        "description": _action_description(record),
        "startTime": iso(record.start_time),
        "endTime": iso(record.end_time),
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
        properties["executionEnvironment"] = single([
            # Id based on the content so identical values are shared between steps in the workflow crate
            crate.add(ContextEntity(crate, "#env-" + _slug(f"{name}-{value}"), properties={
                "@type": "PropertyValue",
                "name": name,
                "value": value,
            }))
            for name, value in record.environment.items()
        ])

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


def _action_description(record: BlockRecord) -> str:
    if record.skipped:
        return "Skipped by the restart property: the outputs come from a previous execution."
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
    }
    identifier = "#" + _slug(f"{software.name}-{software.version}")
    return crate.add(ContextEntity(crate, identifier, properties={k: v for k, v in properties.items() if v}))


def _add_file(crate: ROCrate, file_record: FileRecord):
    properties = {"name": file_record.path.name}
    if file_record.edam_format:
        properties["encodingFormat"] = EDAM_URI + file_record.edam_format
    if file_record.size is not None:
        properties["contentSize"] = str(file_record.size)
    if file_record.sha256:
        properties["sha256"] = file_record.sha256
    if file_record.is_dir:
        return crate.add_dataset(file_record.uri, properties=properties)
    return crate.add_file(file_record.uri, properties=properties)


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9.]+", "-", text).strip("-")
