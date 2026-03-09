"""Pipeline version constant for snapshot compatibility checks.

Bump PIPELINE_VERSION whenever the pipeline changes in a way that would break
resume from an older snapshot:

- Renamed or removed filenames in FilenameEnum (filenames.py)
- New pipeline tasks added or existing tasks removed
- Changed task dependency wiring (DAG structure)
- Changed JSON schemas read/written by pipeline tasks

The MCP plan_resume tool rejects snapshots whose stored pipeline_version
differs from the current value with error code PIPELINE_VERSION_MISMATCH.
"""

PIPELINE_VERSION: int = 1
