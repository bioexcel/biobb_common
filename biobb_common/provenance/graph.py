"""Module containing the functions to draw the graph of a provenance RO-Crate."""
import json
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Optional, Union

from biobb_common.provenance.crate import FAILED, action_environment, action_order, as_list, entity_label, is_restart_skipped

# (name, fill, stroke) of the steps of each machine, when they ran on several machines. Machine 1 keeps the default step colors.
MACHINE_COLORS = [
    ("blue", "#dbeafe", "#1d4ed8"),
    ("green", "#dcfce7", "#15803d"),
    ("amber", "#fef3c7", "#b45309"),
    ("purple", "#f3e8ff", "#7e22ce"),
    ("pink", "#fce7f3", "#be185d"),
    ("cyan", "#cffafe", "#0e7490"),
]
FAILED_STROKE = "#b91c1c"
# Default limits of Mermaid (maxEdges, maxTextSize): it refuses larger graphs
MERMAID_MAX_EDGES = 500
MERMAID_MAX_TEXT = 50000


@dataclass
class Step:
    id: str
    label: str
    failed: bool = False
    # Skipped by the restart property, drawn with a dashed border
    skipped: bool = False
    # Id of the execution environment (machine) where the step ran, None if unknown
    machine: Optional[str] = None


@dataclass
class ProvenanceGraph:
    """Steps (building block executions) and files of an RO-Crate, linked by
    edges file -> step (input) and step -> file (output)."""
    steps: list[Step] = field(default_factory=list)
    files: dict[str, str] = field(default_factory=dict)
    edges: list[tuple[str, str]] = field(default_factory=list)
    # {execution environment id: "Machine <n>: <hostname> (SLURM cluster, job)"}, numbered as in the preview.
    # Steps are colored by machine (with a legend) only if there are several.
    machines: dict[str, str] = field(default_factory=dict)


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
        key=action_order(entities),
    )
    graph = ProvenanceGraph()
    for position, action in enumerate(actions, start=1):
        instrument = entities.get(action["instrument"]["@id"], {})
        # "biobb_gromacs Pdb2gmx" -> "Pdb2gmx"
        label = action.get("alternateName") or instrument.get("name", action["name"]).split()[-1]
        machine, values = action_environment(action, entities)
        if machine and machine not in graph.machines:
            graph.machines[machine] = _machine_label(len(graph.machines) + 1, {v.get("name"): v.get("value") for v in values})
        graph.steps.append(Step(id=action["@id"], label=f"{position}: {label}", failed=action.get("actionStatus") == FAILED,
                                skipped=is_restart_skipped(action), machine=machine or None))
        for key, is_input in (("object", True), ("result", False)):
            for ref in as_list(action.get(key)):
                entity = entities.get(ref["@id"], {})
                if entity.get("@type") not in ("File", "Dataset"):
                    continue
                graph.files[ref["@id"]] = entity_label(entity, ref["@id"])
                graph.edges.append((ref["@id"], action["@id"]) if is_input else (action["@id"], ref["@id"]))
    return graph


def fits_mermaid(graph: ProvenanceGraph) -> bool:
    """Return True if Mermaid draws the graph with its default limits (maxEdges, maxTextSize).
    Larger graphs (ie: workflows with loops) are refused, or are slow to lay out once the limits are raised."""
    return len(graph.edges) <= MERMAID_MAX_EDGES and len(to_mermaid(graph)) <= MERMAID_MAX_TEXT


def summarize(graph: ProvenanceGraph) -> ProvenanceGraph:
    """Return a summary of a graph too large to draw: the repetitions of a step (ie: the iterations of a loop) are one step.

    Steps with the same name, without the prefix of the loop iteration (stateA/frame3/step1_pmx_mutate ->
    step1_pmx_mutate), whose inputs come from the same summary steps (or the same workflow inputs) are
    one step "<position of the first>: <name> ×<n>". The files between steps become edges between the
    steps. The workflow inputs are kept and the outputs are grouped by step and extension: "<name> ×<n>"
    if they have the same name, otherwise "<n> <extension> files".
    """
    step_ids = {step.id for step in graph.steps}
    producer = {target: source for source, target in graph.edges if source in step_ids}
    inputs: dict[str, list[str]] = {}
    for source, target in graph.edges:
        if target in step_ids:
            inputs.setdefault(target, []).append(source)
    consumed = {source for source, target in graph.edges if target in step_ids}
    group_of: dict[str, str] = {}
    groups: dict[tuple, list[Step]] = {}
    for step in graph.steps:
        position, _, label = step.label.partition(": ")
        name = label.rsplit("/", 1)[-1]
        sources = frozenset(group_of.get(producer[f], f) if f in producer else f for f in inputs.get(step.id, []))
        key = (name, sources)
        groups.setdefault(key, []).append(step)
        group_of[step.id] = f"#summary-{list(groups).index(key)}"
    summary = ProvenanceGraph(machines=graph.machines)
    for index, ((name, _), steps) in enumerate(groups.items()):
        position = steps[0].label.partition(": ")[0]
        machines = {s.machine for s in steps}
        summary.steps.append(Step(id=f"#summary-{index}", label=f"{position}: {name}" + (f" ×{len(steps)}" if len(steps) > 1 else ""),
                                  failed=any(s.failed for s in steps), skipped=all(s.skipped for s in steps),
                                  machine=steps[0].machine if len(machines) == 1 else None))
    edges: dict[tuple[str, str], None] = {}
    outputs: dict[tuple[str, str], list[str]] = {}
    for source, target in graph.edges:
        if target in step_ids:
            if source in producer:
                edges[group_of[producer[source]], group_of[target]] = None
            else:
                summary.files[source] = graph.files[source]
                edges[source, group_of[target]] = None
        elif target not in consumed:
            outputs.setdefault((group_of[source], PurePosixPath(graph.files[target].split(" (version ")[0]).suffix), []).append(target)
    for index, ((group, suffix), files) in enumerate(outputs.items()):
        names = {graph.files[f].split(" (version ")[0] for f in files}
        if len(names) == 1:
            label = names.pop() + (f" ×{len(files)}" if len(files) > 1 else "")
        else:
            label = f"{len(files)} {suffix or 'other'} files"
        summary.files[f"#outputs-{index}"] = label
        edges[group, f"#outputs-{index}"] = None
    summary.edges = list(edges)
    return summary


def to_mermaid(graph: ProvenanceGraph) -> str:
    """Return the graph as a Mermaid flowchart. Steps run on several machines are colored by machine, with a legend."""
    ids = _node_ids(graph)
    lines = ["flowchart TD"]
    for step in graph.steps:
        lines.append(f'    {ids[step.id]}["{_escape(step.label)}"]:::{_step_class(graph, step)}')
    for file_id, name in graph.files.items():
        lines.append(f'    {ids[file_id]}[/"{_escape(name)}"/]:::file')
    lines.extend(f"    {ids[source]} --> {ids[target]}" for source, target in graph.edges)
    if _colored(graph):
        lines.append('    subgraph legend["Machines"]')
        lines.extend(f'        legend{i}["{_escape(label)}"]:::machine{i}' for i, label in enumerate(graph.machines.values()))
        lines.append("    end")
    lines.extend([
        "    classDef step fill:#dbeafe,stroke:#1d4ed8",
        f"    classDef failed fill:#fee2e2,stroke:{FAILED_STROKE}",
        "    classDef skipped fill:#f9fafb,stroke:#1d4ed8,stroke-dasharray:5 5",
        "    classDef file fill:#f3f4f6,stroke:#6b7280",
    ])
    if _colored(graph):
        for i in range(len(graph.machines)):
            _, fill, stroke = _machine_color(i)
            lines.append(f"    classDef machine{i} fill:{fill},stroke:{stroke}")
            lines.append(f"    classDef machine{i}failed fill:{fill},stroke:{FAILED_STROKE},stroke-width:3px")
        lines.append("    style legend fill:#ffffff,stroke:#9ca3af")
    return "\n".join(lines) + "\n"


def to_dot(graph: ProvenanceGraph) -> str:
    """Return the graph in Graphviz DOT format. Steps run on several machines are colored by machine, with a legend."""
    ids = _node_ids(graph)
    lines = ["digraph provenance {", "    rankdir=TB;"]
    for step in graph.steps:
        index = _machine_index(graph, step)
        if index is not None:
            _, fill, stroke = _machine_color(index)
        else:
            fill, stroke = {"failed": ("#fee2e2", FAILED_STROKE), "skipped": ("#f9fafb", "#1d4ed8")}.get(_step_class(graph, step), ("#dbeafe", "#1d4ed8"))
        style = "rounded,filled,dashed" if step.skipped else "rounded,filled"
        extra = f', color="{FAILED_STROKE}", penwidth=3' if step.failed else f', color="{stroke}"'
        lines.append(f'    {ids[step.id]} [label="{_escape(step.label)}", shape=box, style="{style}", fillcolor="{fill}"{extra}];')
    for file_id, name in graph.files.items():
        lines.append(f'    {ids[file_id]} [label="{_escape(name)}", shape=note, style=filled, fillcolor="#f3f4f6"];')
    lines.extend(f"    {ids[source]} -> {ids[target]};" for source, target in graph.edges)
    if _colored(graph):
        lines.append('    subgraph cluster_legend {')
        lines.append('        label="Machines"; style=rounded; color="#9ca3af";')
        for i, label in enumerate(graph.machines.values()):
            _, fill, stroke = _machine_color(i)
            lines.append(f'        legend{i} [label="{_escape(label)}", shape=box, style="rounded,filled", fillcolor="{fill}", color="{stroke}"];')
        lines.append("    }")
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


def _machine_label(number: int, environment: dict) -> str:
    """Return the legend label of a machine, ie: "Machine 2: node042 (SLURM cluster mn5, job 123)"."""
    hostname = str(environment.get("hostname") or "").split(".")[0]
    slurm = ", ".join(f"{label} {environment[k]}" for k, label in (("slurm_cluster_name", "SLURM cluster"), ("slurm_job_id", "job")) if environment.get(k))
    return f"Machine {number}" + (f": {hostname}" if hostname else "") + (f" ({slurm})" if slurm else "")


def machine_color(number: int) -> tuple[str, str, str]:
    """Return the (name, fill, stroke) color of the machine <number> (1, 2...) in the graphs."""
    return _machine_color(number - 1)


def _machine_color(index: int) -> tuple[str, str, str]:
    return MACHINE_COLORS[index % len(MACHINE_COLORS)]


def _colored(graph: ProvenanceGraph) -> bool:
    return len(graph.machines) > 1


def _machine_index(graph: ProvenanceGraph, step: Step) -> Optional[int]:
    """Return the index of the machine of a step if the steps are colored by machine."""
    if not _colored(graph) or step.machine not in graph.machines:
        return None
    return list(graph.machines).index(step.machine)


def _step_class(graph: ProvenanceGraph, step: Step) -> str:
    index = _machine_index(graph, step)
    if index is not None:
        return f"machine{index}failed" if step.failed else f"machine{index}"
    return "failed" if step.failed else "skipped" if step.skipped else "step"


def _node_ids(graph: ProvenanceGraph) -> dict[str, str]:
    ids = {step.id: f"step{i}" for i, step in enumerate(graph.steps)}
    ids.update({file_id: f"file{i}" for i, file_id in enumerate(graph.files)})
    return ids


def _escape(text: str) -> str:
    return text.replace('"', "'")
