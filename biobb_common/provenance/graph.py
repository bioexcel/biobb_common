"""Module containing the functions to draw the graph of a provenance RO-Crate."""
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Union

from biobb_common.provenance.crate import FAILED, as_list


@dataclass
class Step:
    id: str
    label: str
    failed: bool = False


@dataclass
class ProvenanceGraph:
    """Steps (building block executions) and files of an RO-Crate, linked by
    edges file -> step (input) and step -> file (output)."""
    steps: list[Step] = field(default_factory=list)
    files: dict[str, str] = field(default_factory=dict)
    edges: list[tuple[str, str]] = field(default_factory=list)


def read_graph(crate_dir: Union[str, Path]) -> ProvenanceGraph:
    """Build the graph of a block or workflow RO-Crate.

    Args:
        crate_dir (str, Path): Directory containing the ro-crate-metadata.json file.
    """
    entities = {e["@id"]: e for e in json.loads((Path(crate_dir) / "ro-crate-metadata.json").read_text())["@graph"]}
    # The workflow run is not a step
    workflows = {i for i, e in entities.items() if "ComputationalWorkflow" in as_list(e.get("@type"))}
    actions = sorted(
        (e for e in entities.values() if e["@type"] == "CreateAction" and e["instrument"]["@id"] not in workflows),
        key=lambda action: action.get("startTime", ""),
    )
    graph = ProvenanceGraph()
    for position, action in enumerate(actions, start=1):
        instrument = entities.get(action["instrument"]["@id"], {})
        # "biobb_gromacs Pdb2gmx" -> "Pdb2gmx"
        label = action.get("alternateName") or instrument.get("name", action["name"]).split()[-1]
        graph.steps.append(Step(id=action["@id"], label=f"{position}: {label}", failed=action.get("actionStatus") == FAILED))
        for key, is_input in (("object", True), ("result", False)):
            for ref in as_list(action.get(key)):
                entity = entities.get(ref["@id"], {})
                if entity.get("@type") not in ("File", "Dataset"):
                    continue
                graph.files[ref["@id"]] = entity.get("name", ref["@id"])
                graph.edges.append((ref["@id"], action["@id"]) if is_input else (action["@id"], ref["@id"]))
    return graph


def to_mermaid(graph: ProvenanceGraph) -> str:
    """Return the graph as a Mermaid flowchart."""
    ids = _node_ids(graph)
    lines = ["flowchart TD"]
    for step in graph.steps:
        lines.append(f'    {ids[step.id]}["{_escape(step.label)}"]:::{"failed" if step.failed else "step"}')
    for file_id, name in graph.files.items():
        lines.append(f'    {ids[file_id]}[/"{_escape(name)}"/]:::file')
    lines.extend(f"    {ids[source]} --> {ids[target]}" for source, target in graph.edges)
    lines.extend([
        "    classDef step fill:#dbeafe,stroke:#1d4ed8",
        "    classDef failed fill:#fee2e2,stroke:#b91c1c",
        "    classDef file fill:#f3f4f6,stroke:#6b7280",
    ])
    return "\n".join(lines) + "\n"


def to_dot(graph: ProvenanceGraph) -> str:
    """Return the graph in Graphviz DOT format."""
    ids = _node_ids(graph)
    lines = ["digraph provenance {", "    rankdir=TB;"]
    for step in graph.steps:
        color = "#fee2e2" if step.failed else "#dbeafe"
        lines.append(f'    {ids[step.id]} [label="{_escape(step.label)}", shape=box, style="rounded,filled", fillcolor="{color}"];')
    for file_id, name in graph.files.items():
        lines.append(f'    {ids[file_id]} [label="{_escape(name)}", shape=note, style=filled, fillcolor="#f3f4f6"];')
    lines.extend(f"    {ids[source]} -> {ids[target]};" for source, target in graph.edges)
    lines.append("}")
    return "\n".join(lines) + "\n"


def write_graph(crate_dir: Union[str, Path], output_path: Union[str, Path]) -> Path:
    """Draw the graph of an RO-Crate, the format depends on the **output_path** extension:
    .mmd (Mermaid), .md (Mermaid inside a Markdown code block), .dot (Graphviz DOT)
    or any format supported by Graphviz (.svg, .png, .pdf...), which requires the
    graphviz Python package and the Graphviz binaries (conda install python-graphviz).
    """
    output_path = Path(output_path)
    graph = read_graph(crate_dir)
    extension = output_path.suffix.lower()
    if extension == ".mmd":
        output_path.write_text(to_mermaid(graph))
    elif extension == ".md":
        output_path.write_text(f"```mermaid\n{to_mermaid(graph)}```\n")
    elif extension in (".dot", ".gv"):
        output_path.write_text(to_dot(graph))
    else:
        try:
            import graphviz
        except ImportError as error:
            raise RuntimeError(f"The graphviz Python package is required to write {extension} files (conda install python-graphviz), "
                               "or use .mmd, .md or .dot instead.") from error
        try:
            output_path.write_bytes(graphviz.Source(to_dot(graph)).pipe(format=extension.lstrip(".")))
        except graphviz.ExecutableNotFound as error:
            raise RuntimeError(f"The Graphviz binaries are required to write {extension} files (conda install python-graphviz), "
                               "or use .mmd, .md or .dot instead.") from error
    return output_path


def _node_ids(graph: ProvenanceGraph) -> dict[str, str]:
    ids = {step.id: f"step{i}" for i, step in enumerate(graph.steps)}
    ids.update({file_id: f"file{i}" for i, file_id in enumerate(graph.files)})
    return ids


def _escape(text: str) -> str:
    return text.replace('"', "'")
