"""Workspace settings."""

from __future__ import annotations

from fastapi import APIRouter

from app.deps import Admin, AnyUser, DbSession
from app.schemas.workspace import WorkspaceOut, WorkspacePatch
from app.services import audit

router = APIRouter(prefix="/workspace", tags=["workspace"])

_FIELDS = ("name", "review_threshold", "default_markup_pct", "scoring_weights")


@router.get("", summary="The caller's workspace settings")
def get_workspace(ctx: AnyUser) -> WorkspaceOut:
    return WorkspaceOut.model_validate(ctx.workspace)


@router.patch("", summary="Update settings (admin)")
def update_workspace(body: WorkspacePatch, ctx: Admin, db: DbSession) -> WorkspaceOut:
    workspace = ctx.workspace
    before = audit.snapshot(workspace, _FIELDS)
    changes = body.model_dump(exclude_unset=True)
    if "scoring_weights" in changes and body.scoring_weights is not None:
        changes["scoring_weights"] = body.scoring_weights.model_dump(exclude_none=True)
    for key, value in changes.items():
        setattr(workspace, key, value)
    db.flush()
    old, new = audit.diff(before, audit.snapshot(workspace, _FIELDS))
    if new:
        audit.record(db, ctx, "workspace.update", workspace, old, new)
    db.commit()
    # Derived values depend on the threshold and weights; recompute is wired by the
    # pipeline package (trips are recomputed lazily on their next change).
    return WorkspaceOut.model_validate(workspace)
