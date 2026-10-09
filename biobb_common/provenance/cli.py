"""Command line interface to merge, draw and validate the provenance RO-Crates."""
import argparse
import sys
from pathlib import Path
from typing import Optional

from biobb_common.provenance.graph import read_graph, to_mermaid, write_graph
from biobb_common.provenance.workflow import find_block_crates, merge_block_crates


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="biobb_provenance", description="Manage the provenance RO-Crates of the biobb executions.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    merge = subparsers.add_parser("merge", help="Merge building block RO-Crates into a workflow RO-Crate.")
    merge.add_argument("crates", nargs="+", help="Block ro-crate-metadata.json files, block crate directories or directories to search for block crates.")
    merge.add_argument("-o", "--output", required=True, help="Directory where the workflow ro-crate-metadata.json will be written.")
    merge.add_argument("-n", "--name", help="Name of the workflow.")
    merge.add_argument("-w", "--workflow-file", help="Python script of the workflow, copied into the output directory.")
    merge.add_argument("-l", "--license", help="License of the workflow script: SPDX identifier (ie: MIT) or URL.")

    graph = subparsers.add_parser("graph", help="Draw the graph of a block or workflow RO-Crate.")
    graph.add_argument("crate", help="Directory containing the ro-crate-metadata.json file.")
    graph.add_argument("-o", "--output", help="Output file: .mmd, .md, .dot or a Graphviz format (.svg, .png...). By default Mermaid is printed.")

    validate = subparsers.add_parser("validate", help="Validate an RO-Crate with rocrate-validator (pip install roc-validator).")
    validate.add_argument("crate", help="Directory containing the ro-crate-metadata.json file.")
    validate.add_argument("-p", "--profile", help="rocrate-validator profile, by default process-run-crate or provenance-run-crate.")
    validate.add_argument("-s", "--severity", default="REQUIRED", choices=["REQUIRED", "RECOMMENDED", "OPTIONAL"], help="Minimum severity of the checks.")

    args = parser.parse_args(argv)

    if args.command == "merge":
        block_crates = _block_crates(args.crates)
        if not block_crates:
            print("No block RO-Crates found.", file=sys.stderr)
            return 1
        if not args.workflow_file:
            print("WARNING: without --workflow-file the crate is not a Workflow RO-Crate, only a Process Run Crate.", file=sys.stderr)
        metadata_path = merge_block_crates(block_crates, args.output, workflow_file=args.workflow_file, name=args.name, license=args.license)
        print(f"Workflow RO-Crate with {len(block_crates)} steps written to: {metadata_path}")
    elif args.command == "graph":
        if args.output:
            print(f"Graph written to: {write_graph(args.crate, args.output)}")
        else:
            print(to_mermaid(read_graph(args.crate)), end="")
    elif args.command == "validate":
        from biobb_common.provenance.validation import validate_crate
        issues = validate_crate(args.crate, profile=args.profile, severity=args.severity)
        for issue in issues:
            print(issue)
        print("Valid RO-Crate" if not issues else f"{len(issues)} issues found")
        return 1 if issues else 0
    return 0


def _block_crates(paths: list[str]) -> list[Path]:
    """Resolve the merge arguments to block ro-crate-metadata.json files."""
    block_crates: list[Path] = []
    for path in map(Path, paths):
        if path.is_file():
            block_crates.append(path)
        elif (path / "ro-crate-metadata.json").is_file() and path.parent.name == "provenance":
            block_crates.append(path / "ro-crate-metadata.json")
        else:
            block_crates.extend(find_block_crates(path))
    return list(dict.fromkeys(block_crates))


if __name__ == "__main__":
    sys.exit(main())
