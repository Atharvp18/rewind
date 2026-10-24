"""Shared message schemas (tech spec Part 0, section 0.5).

This is the contract between the app (Nak), the API (Atharv), and the
vision/lookup/eligibility modules (Tiea). Field names must not change
without all three owners agreeing. Money is always integer cents.
"""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel


class VisionExtract(BaseModel):
    name: str | None = None
    brand: str | None = None
    size: str | None = None
    upc: str | None = None
    shelf_price_cents: int | None = None
    category: str | None = None
    is_medication: bool = False
    is_prescription_only: bool | None = None
    package_eligibility_marking: Literal["eligible", "none_seen"] | None = None
    field_confidence: dict[str, float] = {}
    warnings: list[str] = []
    raw_model: Literal["claude", "gemini"] = "claude"


class ProductResolution(BaseModel):
    product_key: str
    upc: str | None = None
    name: str
    brand: str | None = None
    size: str | None = None
    category: str
    is_medication: bool = False
    is_prescription_only: bool = False
    amount_cents: int | None = None
    price_source: Literal["shelf_tag", "cache", "user_spoken", "seeded"] | None = None
    state: Literal["resolved", "partial", "unresolved"] = "unresolved"
    warnings: list[str] = []


class EligibilityResult(BaseModel):
    label: Literal["eligible", "not_eligible", "could_not_confirm"]
    confidence: float | None = None
    basis: Literal[
        "upc_match",
        "semantic_match",
        "irs_category_rule",
        "package_disagreement",
        "no_match",
        "index_unavailable",
    ]
    source: Literal["retailer_index", "irs_rules", "hand_entered"] | None = None
    collected_at: str | None = None
    matched_name: str | None = None


class ScanResult(BaseModel):
    scan_id: str
    timestamp: str
    state: Literal["resolved", "partial", "unresolved"]
    product: ProductResolution
    eligibility: EligibilityResult
    warnings: list[str] = []


class Reroute(BaseModel):
    from_card_id: str
    to_card_id: str
    reason: Literal["insufficient_balance", "group_exceeds_balance", "user_choice"]


class PaymentRecommendation(BaseModel):
    scan_id: str
    decision: Literal["route_to_hsa", "route_to_general", "ask_user", "blocked"]
    card_id: str | None = None
    amount_cents: int
    amount_basis: Literal["shelf_price", "remaining_after_copay"]
    balance_before_cents: int | None = None
    balance_after_cents: int | None = None
    reroute: Reroute | None = None
    requires_confirmation: bool = True
    reason_code: str
    card_options: list[str] = []


class VoiceRequest(BaseModel):
    request_id: str
    prompt_id: str | None = None
    text: str
    priority: Literal["alert", "normal"] = "normal"
    expects_response: bool = False
    response_scope: Literal[
        "confirm_add",
        "choose_card",
        "confirm_checkout",
        "confirm_clear_cart",
        "confirm_strength",
        "none",
    ] = "none"
    sentences: list[str] = []


class ScanResponse(BaseModel):
    scan: ScanResult
    recommendation: PaymentRecommendation | None = None
    voice: VoiceRequest
