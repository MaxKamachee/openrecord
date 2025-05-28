from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from datetime import datetime
from enum import Enum

class OPRACategory(str, Enum):
    PRIVACY_INTEREST = "N.J.S.A. 47:1A-1"
    PERSONAL_IDENTIFYING = "N.J.S.A. 47:1A-1.1(20)"
    CRIMINAL_INVESTIGATORY = "N.J.S.A. 47:1A-1.1(5)"
    HIPAA_DATA = "N.J.S.A. 47:1A-1.1(28)"
    ATTORNEY_CLIENT = "N.J.S.A. 47:1A-1.1(9)"
    JUVENILE_INFO = "N.J.S.A. 47:1A-1.1(23)"
    # Add more as needed

class DetectionResult(BaseModel):
    text: str = Field(..., description="The text that should be redacted")
    category: OPRACategory = Field(..., description="OPRA exemption category")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score 0-1")
    page_number: int = Field(..., ge=0, description="Page number (0-indexed)")
    start_pos: int = Field(..., ge=0, description="Start position in text")
    end_pos: int = Field(..., ge=0, description="End position in text")
    detection_reason: str = Field(..., description="Why this was flagged for redaction")
    pattern_name: Optional[str] = Field(None, description="Pattern that matched")
    context: Optional[str] = Field(None, description="Surrounding context")
    approved: bool = Field(True, description="Whether redaction is approved")

class RedactionConfig(BaseModel):
    document_type: str = Field("general", description="Type of document being processed")
    confidence_threshold: float = Field(0.6, ge=0.0, le=1.0)
    enabled_categories: List[OPRACategory] = Field(default_factory=list)
    use_ai_detection: bool = Field(True)
    use_pattern_detection: bool = Field(True)
    use_context_analysis: bool = Field(True)

class AnalysisStatistics(BaseModel):
    total_detections: int
    high_confidence_count: int
    categories_found: List[OPRACategory]
    pages_with_detections: List[int]
    processing_time: float

class DocumentAnalysis(BaseModel):
    detections: List[DetectionResult]
    statistics: AnalysisStatistics
    processing_time: float
    document_metadata: Dict[str, Any]

# OPRA Categories mapping
OPRA_CATEGORIES = {
    OPRACategory.PERSONAL_IDENTIFYING: {
        "name": "Personal Identifying Information",
        "description": "SSNs, home addresses, credit cards, etc.",
        "examples": ["Social Security numbers", "home addresses", "credit card numbers"]
    },
    OPRACategory.CRIMINAL_INVESTIGATORY: {
        "name": "Criminal Investigatory Records",
        "description": "Records pertaining to criminal investigations",
        "examples": ["Detective notes", "surveillance footage", "confidential informant statements"]
    },
    OPRACategory.HIPAA_DATA: {
        "name": "HIPAA Data",
        "description": "Medical and health information",
        "examples": ["Patient records", "medical test results", "prescription information"]
    }
}