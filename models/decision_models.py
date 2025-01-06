# decision_models.py

from enum import Enum
from pydantic import BaseModel, Field
from typing import List

class ConditionOutcomeEnum(str, Enum):
    granted = "granted"
    denied = "denied"
    remanded = "remanded"
    dismissed = "dismissed"
    referred = "referred"
    withdrawn = "withdrawn"
    moot = "moot"
    partial_grant = "partial_grant"

class ConditionDetail(BaseModel):
    condition_name: str = Field(..., description="Name of the claimed condition.")
    outcome: ConditionOutcomeEnum = Field(..., description="Outcome of the claim for this condition (granted, denied, remanded, etc.).")
    specific_reasoning: str = Field(..., description="Reasoning provided by the judge for this specific condition outcome.")

    class Config:
        extra = "forbid"

class EvidenceItem(BaseModel):
    evidence_type: str = Field(..., description="Type of evidence (e.g., DBQ, lay statement, C&P exam report).")
    description: str = Field(..., description="Brief description of the evidence considered.")
    relevance: str = Field(..., description="How this evidence contributed to the decision.")

    class Config:
        extra = "forbid"

class LegalRationale(BaseModel):
    legal_citation: str = Field(..., description="Specific legal standards or citations referenced.")
    rationale_text: str = Field(..., description="Explanation provided by the judge.")

    class Config:
        extra = "forbid"

class FindingOfFact(BaseModel):
    text: str = Field(..., description="A specific finding of fact made by the judge.")

    class Config:
        extra = "forbid"

class ParticipantDetail(BaseModel):
    name: str = Field(..., description="Name of the participant (e.g., judge, representative).")
    role: str = Field(..., description="Role in the decision (e.g., VLJ, Veteran's representative).")

    class Config:
        extra = "forbid"

class ReferralDetail(BaseModel):
    issue: str = Field(..., description="The issue that was referred.")
    reason: str = Field(..., description="Reason for the referral.")

    class Config:
        extra = "forbid"

class BvaDecisionStructuredSummary(BaseModel):
    decision_citation: str = Field(..., description="The citation of the BVA decision.")
    decision_date: str = Field(..., description="The date the decision was issued.")
    hearing_date: str = Field(..., description="The date of the Veteran's hearing, if applicable.")
    granted_conditions: List[ConditionDetail] = Field(..., description="Conditions that were granted.")
    remanded_conditions: List[ConditionDetail] = Field(..., description="Conditions that were remanded.")
    denied_conditions: List[ConditionDetail] = Field(..., description="Conditions that were denied.")
    dismissed_conditions: List[ConditionDetail] = Field(..., description="Conditions that were dismissed.")
    referred_issues: List[ReferralDetail] = Field(..., description="Issues referred to the AOJ for adjudication.")
    findings_of_fact: List[FindingOfFact] = Field(..., description="Findings of fact determined by the judge.")
    legal_rationale: List[LegalRationale] = Field(..., description="List of legal standards and judge's rationale.")
    evidence: List[EvidenceItem] = Field(..., description="A list of key evidence items considered in the decision.")
    reasoning_overall: str = Field(..., description="Overall reasoning or rationale of the judge's decision.")
    participants: List[ParticipantDetail] = Field(..., description="List of participants involved in the decision.")

    class Config:
        extra = "forbid"
