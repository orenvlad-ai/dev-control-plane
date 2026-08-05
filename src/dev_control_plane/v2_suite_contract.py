"""Exact authoritative fake-first suite membership for Orchestrator v2."""

from __future__ import annotations


V2_SMOKES = (
    "apps/dev_control_plane_v2_registry_smoke.py",
    "apps/dev_control_plane_codex_app_server_v2_smoke.py",
    "apps/dev_control_plane_arbiter_v2_smoke.py",
    "apps/dev_control_plane_projection_v2_smoke.py",
    "apps/dev_control_plane_supervisor_v2_smoke.py",
    "apps/dev_control_plane_supervisor_runtime_v2_smoke.py",
    "apps/dev_control_plane_contour_verifier_v2_smoke.py",
    "apps/dev_control_plane_release_train_v2_smoke.py",
    "apps/dev_control_plane_wb_core_release_adapter_v2_smoke.py",
    "apps/dev_control_plane_local_install_v2_smoke.py",
    "apps/dev_control_plane_migration_v2_smoke.py",
    "apps/dev_control_plane_hosted_deploy_smoke.py",
)

RETAINED_SAFETY_SMOKES = (
    "apps/dev_control_plane_state_layout_smoke.py",
    "apps/dev_control_plane_mcp_no_legacy_tools_smoke.py",
    "apps/dev_control_plane_mcp_no_legacy_fallback_smoke.py",
    "apps/dev_control_plane_github_closure_smoke.py",
    "apps/dev_control_plane_github_closure_workflow_smoke.py",
    "apps/dev_control_plane_secrets_smoke.py",
    "apps/dev_control_plane_target_remote_source_smoke.py",
)

AUTHORITATIVE_SMOKES = (*V2_SMOKES, *RETAINED_SAFETY_SMOKES)
AUTHORITATIVE_NON_SMOKE_CHECKS = 2  # compile plus static policy
AUTHORITATIVE_CHECK_COUNT = len(AUTHORITATIVE_SMOKES) + AUTHORITATIVE_NON_SMOKE_CHECKS

if len(set(AUTHORITATIVE_SMOKES)) != len(AUTHORITATIVE_SMOKES):
    raise RuntimeError("authoritative v2 suite contract contains duplicate members")
