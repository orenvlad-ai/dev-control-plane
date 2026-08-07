"""Deliberately non-installing build backend.

The laboratory artifact is built by scripts/build_artifact.py. Keeping this
stub dependency-free prevents generic package tooling from fetching a backend.
"""


def build_wheel(*_args, **_kwargs):  # pragma: no cover - defensive interface
    raise RuntimeError("use scripts/build_artifact.py for the DCP lab artifact")
