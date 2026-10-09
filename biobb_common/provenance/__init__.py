from biobb_common.provenance.tracker import track

name = "provenance"
__all__ = ["track", "find_block_crates", "merge_block_crates", "workflow_provenance"]


def __getattr__(attribute):
    # Lazy import so rocrate is only loaded when provenance is used
    if attribute in ("find_block_crates", "merge_block_crates", "workflow_provenance"):
        from biobb_common.provenance import workflow
        return getattr(workflow, attribute)
    raise AttributeError(f"module {__name__!r} has no attribute {attribute!r}")
