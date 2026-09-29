"""ORM models. Importing this package registers every table on `Base.metadata`."""

from app.models.audit import AuditEvent
from app.models.base import Base, Timestamps, UUIDPk, WorkspaceScoped
from app.models.document import ProcessingEvent, SourceDocument
from app.models.flag import Flag
from app.models.intelligence import FeeObservation, Recommendation
from app.models.operator import Operator
from app.models.proposal import Proposal, ProposalOption
from app.models.quote import FeeLine, Quote, QuoteField
from app.models.trip import Trip, TripLeg, TripOperator
from app.models.workspace import Invite, User, Workspace

__all__ = [
    "AuditEvent",
    "Base",
    "FeeLine",
    "FeeObservation",
    "Flag",
    "Invite",
    "Operator",
    "ProcessingEvent",
    "Proposal",
    "ProposalOption",
    "Quote",
    "QuoteField",
    "Recommendation",
    "SourceDocument",
    "Timestamps",
    "Trip",
    "TripLeg",
    "TripOperator",
    "UUIDPk",
    "User",
    "Workspace",
    "WorkspaceScoped",
]
