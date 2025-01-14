from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class PharmacyInfo(BaseModel):
    """Pharmacy information from response"""

    id: UUID
    name: str
    npi: str
    nabp: str
    dea: str
    state: str
    zip_code: str


class RejectInfo(BaseModel):
    """Reject information from response"""

    code: str
    message: str
    details: str


class EventLogEntry(BaseModel):
    """Individual log entry in event log"""

    Level: str
    Message: str
    Time: datetime
    Data: dict[str, Any]


class EventLog(BaseModel):
    """Event log section of response"""

    other: list[EventLogEntry]

    # Dynamic field names
    model_config = {"extra": "allow"}  # Allow additional fields beyond those explicitly defined


class HandlerSourceInfo(BaseModel):
    """Handler source information"""

    HandlerID: UUID
    SourceType: str
    SourceID: UUID
    PharmacyNetworkID: UUID
    ProcessRuleID: UUID
    ProcessRuleName: str


class TransactionContext(BaseModel):
    """Main transaction context from response"""

    authorization_number: str
    used_cardholder: str | None = None
    used_group: str | None = None
    used_subgroup: str | None = None

    # Reuse existing header model fields where possible
    header: dict[str, Any]  # Complex nested structure
    insurance: dict[str, Any]
    pricing: dict[str, Any]
    claim: dict[str, Any]

    compound: Any | None = None
    daw_difference: int = 0
    pay_ingredient_cost: float = 0
    bill_ingredient_cost: float = 0
    tax_info: Any | None = None
    compound_cost_floor: float = 0
    main_drug: Any | None = None

    # Pharmacy information
    pharmacy: PharmacyInfo

    # Reject information
    rejects: list[RejectInfo]

    # Event logging
    event_log: EventLog

    # Transaction identification
    transaction_id: UUID
    claim_id: UUID
    transaction_status: str

    # Handler source mapping
    handler_source_map: dict[str, HandlerSourceInfo]

    # Additional fields with defaults
    is_mail_order: bool = False
    web_pricing: bool = True

    model_config = {"extra": "allow"}  # Allow additional fields we haven't explicitly modeled


class ClaimResponse(BaseModel):
    """Top level response model"""

    transaction: str
    message_id: UUID
    transaction_context: TransactionContext
    is_debug: bool | None = None
    web_pricing: bool | None = None
    log_level: str | None = None
    rules_execution_range: dict[str, int] | None = None
    batch_id: str | None = None
