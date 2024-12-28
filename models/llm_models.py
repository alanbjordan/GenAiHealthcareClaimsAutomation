# models/llm_models.py

from enum import Enum
from pydantic import BaseModel, Field
from typing import List, Optional

class DocumentType(str, Enum):
    Military_Personnel_Records = "Military Personnel Records"
    Clinical_Records = "Clinical Records"
    Legal_Documents = "Legal Documents"
    Decision_Letter = "Decision Letters"
    Notification_Letter = "Notification Letters"
    Financial_Documents = "Financial Documents"
    Education_Materials = "Education Materials"
    Correspondence = "Correspondence"
    Award_Letter = "Award Letters"
    DD214 = 'DD214'
    Disability_Application = "Disability Applications"
    Unclassified = "Unclassified"  

class PageClassification(BaseModel):
    category: DocumentType = Field(..., description="The category of the document.")
    confidence: float = Field(None, description="Model's confidence score for the classification")
    document_date: str = Field(None, description="The date of the document")  # New field for document date
    page_number: int = Field(..., description="The order of the page in the document as a number.")

    class Config:
            extra = 'forbid'  # Disallow additional properties to match JSON schema rules

class PageClassifications(BaseModel):
    pages: List[PageClassification]

    class Config:
        extra = 'forbid'  # Disallow additional properties for strict schema adherence

class MilitaryPersonnelRecord(BaseModel):
    category: DocumentType = Field(DocumentType.Military_Personnel_Records, description="The category of the document")  
    service_member_name: Optional[str]
    service_branch: Optional[str]
    service_number: Optional[str]
    rank: Optional[str]
    dates_of_service: Optional[List[str]]
    assignments: Optional[List[str]]  # Military assignments or units
    awards_and_decorations: Optional[List[str]]
    discharge_status: Optional[str]
    notes: Optional[str]
    class Config:
        use_enum_values = True

class DiagnosisDetails(BaseModel):
    diagnosis_name:Optional[str]
    medication_list:Optional[List[str]]
    treatments: Optional[str]  # List of treatments/medications for this visit
    findings: Optional[str]  # Key findings, lab results, etc., for this visit
    doctor_comments: Optional[str]  # Comments specific to this visit

class VisitDetails(BaseModel):
    date_of_visit: Optional[str]  # Date of medical visit
    diagnosis: Optional[List[DiagnosisDetails]]  # List of identified diagnoses for this visit
    medical_professionals: Optional[List[str]]  # Names of professionals involved in this visit

class ClinicalRecord(BaseModel):
    patient_name: Optional[str]  # Name of the patients
    visits: Optional[List[VisitDetails]]  # List of visits and their respective details

    class Config:
        use_enum_values = True

class LegalDocument(BaseModel):
    category: DocumentType = Field(DocumentType.Legal_Documents, description="The category of the document")  
    document_title: Optional[str]
    parties_involved: Optional[List[str]]
    date_filed: Optional[str]
    case_number: Optional[str]
    legal_issue: Optional[str]
    summary: Optional[str]
    notes: Optional[str]
    class Config:
        use_enum_values = True

class DecisionLetter(BaseModel):
    category: DocumentType = Field(DocumentType.Decision_Letter, description="The category of the document")  
    decision_date: Optional[str]
    claimant_name: Optional[str]
    decision_summary: Optional[str]
    benefits_awarded: Optional[List[str]]
    benefits_denied: Optional[List[str]]
    effective_date: Optional[str]
    appeal_rights_information: Optional[str]
    notes: Optional[str]
    class Config:
        use_enum_values = True

class NotificationLetter(BaseModel):
    category: DocumentType = Field(DocumentType.Notification_Letter, description="The category of the document")  
    notification_date: Optional[str]
    recipient_name: Optional[str]
    notification_subject: Optional[str]
    notification_body: Optional[str]
    action_required: Optional[str]
    notes: Optional[str]
    class Config:
        use_enum_values = True

class FinancialDocument(BaseModel):
    category: DocumentType = Field(DocumentType.Financial_Documents, description="The category of the document")  
    document_date: Optional[str]
    account_holder_name: Optional[str]
    account_number: Optional[str]
    transaction_details: Optional[List[str]]
    amounts: Optional[List[float]]
    total_amount: Optional[float]
    notes: Optional[str]
    class Config:
        use_enum_values = True

class EducationMaterial(BaseModel):
    category: DocumentType = Field(DocumentType.Education_Materials, description="The category of the document")  
    document_title: Optional[str]
    author: Optional[str]
    publication_date: Optional[str]
    topics_covered: Optional[List[str]]
    summary: Optional[str]
    notes: Optional[str]
    class Config:
        use_enum_values = True

class Correspondence(BaseModel):
    category: DocumentType = Field(DocumentType.Correspondence, description="The category of the document")  
    sender_name: Optional[str]
    recipient_name: Optional[str]
    date_sent: Optional[str]
    subject: Optional[str]
    message_body: Optional[str]
    method_of_communication: Optional[str]  # e.g., email, letter
    notes: Optional[str]
    class Config:
        use_enum_values = True

class AwardLetter(BaseModel):
    category: DocumentType = Field(DocumentType.Award_Letter, description="The category of the document")  
    award_date: Optional[str]
    recipient_name: Optional[str]
    award_type: Optional[str]
    award_description: Optional[str]
    effective_date: Optional[str]
    monetary_amount: Optional[float]
    notes: Optional[str]
    class Config:
        use_enum_values = True

class ServicePeriodModel(BaseModel):
    startDate: str = Field(..., description="Start date of the service period in YYYY-MM-DD format.")
    endDate: str = Field(..., description="End date of the service period in YYYY-MM-DD format.")
    branchOfService: Optional[str] = Field(None, description="Branch of service.")

class DD214Record(BaseModel):
    category: DocumentType = Field(DocumentType.DD214, description="The category of the document")  
    service_member_name: Optional[str]
    service_number: Optional[str]
    rank_at_discharge: Optional[str]
    service_periods: List[ServicePeriodModel] = Field(..., description="List of service periods extracted from DD214.")
    place_of_entry: Optional[str]
    place_of_separation: Optional[str]
    military_occupational_specialty: Optional[str]
    decorations_medals_badges: Optional[List[str]]
    discharge_type: Optional[str]  # e.g., Honorable, General
    reentry_code: Optional[str]
    separation_code: Optional[str]
    narrative_reason_for_separation: Optional[str]
    notes: Optional[str]
    class Config:
        use_enum_values = True
        extra = 'forbid'

class DisabilityApplication(BaseModel):
    category: DocumentType = Field(DocumentType.Disability_Application, description="The category of the document")  
    applicant_name: Optional[str]
    application_date: Optional[str]
    claimed_conditions: Optional[List[str]]
    evidence_provided: Optional[List[str]]
    representative_name: Optional[str]
    contact_information: Optional[str]
    notes: Optional[str]
    class Config:
        use_enum_values = True

class UnclassifiedDocument(BaseModel):
    category: DocumentType = Field(DocumentType.Unclassified, description="The category of the document")  
    document_title: Optional[str]
    content_summary: Optional[str]
    date_created: Optional[str]
    notes: Optional[str]
    class Config:
        use_enum_values = True

class ConditionOutcomeEnum(str, Enum):
    granted = "granted"
    denied = "denied"
    remanded = "remanded"
    dismissed = "dismissed"
    # Add other possible outcomes if relevant.

class ConditionDetail(BaseModel):
    condition_name: str = Field(..., description="Name of the claimed condition.")
    outcome: ConditionOutcomeEnum = Field(..., description="Outcome of the claim for this condition (granted, denied, remanded, etc.).")
    specific_reasoning: Optional[str] = Field(None, description="Reasoning provided by the judge for this specific condition outcome.")

class EvidenceItem(BaseModel):
    evidence_type: Optional[str] = Field(None, description="Type of evidence (e.g., DBQ, lay statement, C&P exam report).")
    description: Optional[str] = Field(None, description="Brief description of the evidence considered.")

class BvaDecisionStructuredSummary(BaseModel):
    decision_citation: str = Field(..., description="The citation of the BVA decision.")
    conditions: List[ConditionDetail] = Field(..., description="A list of claimed conditions and their outcomes.")
    reasoning_overall: Optional[str] = Field(None, description="Overall reasoning or rationale of the judge's decision.")
    evidence: Optional[List[EvidenceItem]] = Field(None, description="A list of key evidence items considered in the decision.")

'''
class ServiceTreatmentRecord(BaseModel):
    category: DocumentType = Field(DocumentType.Service_Treatment_Records, description="The category of the document")    
    service_member_name: Optional[str]
    service_branch: Optional[str]
    service_number: Optional[str]
    dates_of_service: Optional[List[str]]
    medical_conditions: Optional[List[str]]  # List of medical conditions noted
    treatments_received: Optional[List[str]]
    injuries_reported: Optional[List[str]]
    notes: Optional[str]  # Any additional notes
    class Config:
        use_enum_values = True
'''
