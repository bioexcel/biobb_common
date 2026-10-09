"""Module containing the function to validate the provenance RO-Crates with rocrate-validator.

rocrate-validator is not a dependency of biobb_common, install it with: pip install roc-validator
"""
import json
from pathlib import Path
from typing import Optional, Union

PROVENANCE_RUN_CRATE = "https://w3id.org/ro/wfrun/provenance/0.5"


def validate_crate(crate_dir: Union[str, Path], profile: Optional[str] = None, severity: str = "REQUIRED") -> list[str]:
    """Validate an RO-Crate and return the list of issues, empty if the crate is valid.

    Args:
        crate_dir (str, Path): Directory containing the ro-crate-metadata.json file.
        profile (str): (None) rocrate-validator profile identifier. By default
            "provenance-run-crate" for workflow crates and "process-run-crate" for block crates.
        severity (str): ("REQUIRED") Minimum severity of the checked requirements: REQUIRED, RECOMMENDED or OPTIONAL.

    Returns:
        list: Issues found, as "<severity> | <check name> | <message>" strings.
    """
    try:
        from rocrate_validator import services
        from rocrate_validator.models import Severity, ValidationSettings
    except ImportError as error:
        raise ImportError("rocrate-validator is required to validate RO-Crates: pip install roc-validator") from error

    crate_dir = Path(crate_dir).resolve()
    profile = profile or _default_profile(crate_dir)
    result = services.validate(ValidationSettings(
        rocrate_uri=str(crate_dir),
        profile_identifier=profile,
        requirement_severity=Severity[severity.upper()],
    ))
    issues = [f"{issue.severity.name} | {issue.check.name} | {issue.message}" for issue in result.get_issues()]
    return list(dict.fromkeys(issues))


def _default_profile(crate_dir: Path) -> str:
    graph = json.loads((crate_dir / "ro-crate-metadata.json").read_text())["@graph"]
    root = next(e for e in graph if e["@id"] == "./")
    conforms_to = root.get("conformsTo", [])
    conforms_to = conforms_to if isinstance(conforms_to, list) else [conforms_to]
    if {"@id": PROVENANCE_RUN_CRATE} in conforms_to:
        return "provenance-run-crate"
    return "process-run-crate"
