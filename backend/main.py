import os
import re
import json
import uuid
import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from io import BytesIO

import fitz  # PyMuPDF
import anthropic
from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv

from models import (
    DetectionResult, 
    RedactionConfig, 
    DocumentAnalysis, 
    AnalysisStatistics,
    OPRACategory, 
    OPRA_CATEGORIES
)

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Claude client
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    logger.error("ANTHROPIC_API_KEY not found in environment variables!")
    raise ValueError("ANTHROPIC_API_KEY is required for AI detection")

claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
logger.info("Claude AI client initialized successfully")

# FastAPI app
app = FastAPI(
    title="OpenRecord API",
    description="AI-powered document redaction system for municipalities using Claude AI",
    version="2.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory storage (use database in production)
document_store = {}
analysis_store = {}

class AdvancedClaudeDetector:
    """Claude AI-powered detection engine for OPRA compliance"""
    
    def __init__(self):
        self.client = claude_client
        self.model = "claude-3-sonnet-20240229"
        
        # Comprehensive regex patterns as backup/supplement to AI
        self.patterns = {
            "ssn": {
                "regex": r'\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b',
                "category": OPRACategory.PERSONAL_IDENTIFYING,
                "confidence": 0.95
            },
            "phone": {
                "regex": r'\b(?:\+?1[-.\s]?)?\(?[2-9][0-9]{2}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b',
                "category": OPRACategory.PERSONAL_IDENTIFYING,
                "confidence": 0.85
            },
            "email": {
                "regex": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
                "category": OPRACategory.PERSONAL_IDENTIFYING,
                "confidence": 0.90
            },
            "credit_card": {
                "regex": r'\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|3[0-9]{13}|6(?:011|5[0-9]{2})[0-9]{12})\b',
                "category": OPRACategory.PERSONAL_IDENTIFYING,
                "confidence": 0.98
            },
            "drivers_license": {
                "regex": r'\b[A-Z]\d{13,14}\b',
                "category": OPRACategory.PERSONAL_IDENTIFYING,
                "confidence": 0.85
            },
            "address": {
                "regex": r'\b\d+\s+[A-Za-z0-9\s,.-]+(?:street|st|avenue|ave|road|rd|drive|dr|lane|ln|boulevard|blvd|way|place|pl|court|ct)\b',
                "category": OPRACategory.PERSONAL_IDENTIFYING,
                "confidence": 0.75
            },
            "case_number": {
                "regex": r'\b(?:case|docket|file|complaint)[\s#]*:?\s*[A-Z0-9\-]{4,20}\b',
                "category": OPRACategory.CRIMINAL_INVESTIGATORY,
                "confidence": 0.80
            },
            "officer_badge": {
                "regex": r'\b(?:officer|badge|patrol|detective)[\s#]*:?\s*[A-Z0-9]{2,8}\b',
                "category": OPRACategory.CRIMINAL_INVESTIGATORY,
                "confidence": 0.85
            },
            "medical_record": {
                "regex": r'\b(?:MRN|MR|medical record)[\s#]*:?\s*[A-Z0-9]{6,12}\b',
                "category": OPRACategory.HIPAA_DATA,
                "confidence": 0.90
            },
            "date_of_birth": {
                "regex": r'\b(?:DOB|date of birth|born)[\s:]*(?:0?[1-9]|1[0-2])[/\-](?:0?[1-9]|[12][0-9]|3[01])[/\-](?:19|20)?\d{2,4}\b',
                "category": OPRACategory.PERSONAL_IDENTIFYING,
                "confidence": 0.90
            }
        }
    
    async def detect_with_claude(self, text: str, page_num: int, document_type: str) -> List[DetectionResult]:
        """Use Claude AI for intelligent, context-aware detection"""
        detections = []
        
        if not text.strip():
            return detections
        
        # Build comprehensive prompt for Claude
        prompt = self._build_claude_prompt(text, document_type)
        
        try:
            response = await asyncio.to_thread(
                self.client.messages.create,
                model=self.model,
                max_tokens=4000,
                temperature=0.1,  # Low temperature for consistent results
                messages=[{"role": "user", "content": prompt}]
            )
            
            # Parse Claude's response
            ai_detections = self._parse_claude_response(response.content[0].text, text, page_num)
            detections.extend(ai_detections)
            
            logger.info(f"Claude AI detected {len(ai_detections)} items on page {page_num}")
            
        except Exception as e:
            logger.error(f"Claude AI detection failed: {e}")
            # Continue with pattern detection as fallback
        
        return detections
    
    def detect_with_patterns(self, text: str, page_num: int) -> List[DetectionResult]:
        """Pattern-based detection as backup/supplement"""
        detections = []
        
        for pattern_name, pattern_info in self.patterns.items():
            try:
                matches = re.finditer(pattern_info["regex"], text, re.IGNORECASE | re.MULTILINE)
                for match in matches:
                    # Get context around the match
                    start_context = max(0, match.start() - 50)
                    end_context = min(len(text), match.end() + 50)
                    context = text[start_context:end_context]
                    
                    detection = DetectionResult(
                        text=match.group().strip(),
                        category=pattern_info["category"],
                        confidence=pattern_info["confidence"],
                        page_number=page_num,
                        start_pos=match.start(),
                        end_pos=match.end(),
                        detection_reason=f"Pattern match: {pattern_name}",
                        pattern_name=pattern_name,
                        context=context
                    )
                    detections.append(detection)
                    
            except re.error as e:
                logger.warning(f"Regex error for pattern {pattern_name}: {e}")
                continue
        
        return detections
    
    def _build_claude_prompt(self, text: str, document_type: str) -> str:
        """Build comprehensive prompt for Claude AI"""
        
        opra_categories_text = "\n".join([
            f"**{category.value}**: {info['name']} - {info['description']}"
            for category, info in OPRA_CATEGORIES.items()
        ])
        
        prompt = f"""You are an expert in New Jersey Open Public Records Act (OPRA) compliance, specifically trained to identify information that must be redacted from public documents according to NJ state law.

DOCUMENT TYPE: {document_type}

ACTIVE OPRA EXEMPTION CATEGORIES:
{opra_categories_text}

ANALYSIS INSTRUCTIONS:
1. Carefully analyze the following document text
2. Identify ANY information that falls under OPRA exemption categories
3. Pay special attention to:
   - Personal Identifying Information (SSNs, addresses, phone numbers, dates of birth, driver's license numbers)
   - Names of individuals in sensitive contexts (defendants, victims, witnesses, minors)
   - Medical information and HIPAA-protected data
   - Criminal investigation details and case information
   - Attorney-client privileged communications
   - Any information that could compromise privacy or ongoing investigations

4. For each detection, provide:
   - The exact text to be redacted
   - The specific OPRA category (use exact codes like "N.J.S.A. 47:1A-1.1(20)")
   - Confidence level (0.0 to 1.0) - be conservative but thorough
   - Brief reason for redaction
   - Character position in text (estimate start and end positions)

IMPORTANT GUIDELINES:
- Be thorough but precise - identify all sensitive information
- Consider context - names, numbers, and addresses in official documents likely need redaction
- When in doubt about borderline cases, err on the side of protection
- Focus on information that would violate privacy or compromise investigations

RESPONSE FORMAT:
Return your analysis as a JSON array with this exact structure:
[
  {{
    "text": "exact text to redact",
    "category": "N.J.S.A. 47:1A-1.1(20)",
    "confidence": 0.95,
    "reason": "Social Security Number - Personal Identifying Information",
    "start_pos": 123,
    "end_pos": 134
  }}
]

DOCUMENT TEXT TO ANALYZE:
---
{text}
---

Please analyze this document and return ONLY the JSON array of redactions (no other text or formatting):"""

        return prompt
    
    def _parse_claude_response(self, response_text: str, original_text: str, page_num: int) -> List[DetectionResult]:
        """Parse Claude's JSON response into DetectionResult objects"""
        detections = []
        
        try:
            # Clean up response text
            response_text = response_text.strip()
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]
            response_text = response_text.strip()
            
            # Handle case where Claude returns explanation before JSON
            if not response_text.startswith('['):
                # Try to find JSON array in the response
                json_start = response_text.find('[')
                json_end = response_text.rfind(']') + 1
                if json_start != -1 and json_end != -1:
                    response_text = response_text[json_start:json_end]
            
            # Parse JSON
            claude_detections = json.loads(response_text)
            
            for detection_data in claude_detections:
                try:
                    text = detection_data.get("text", "").strip()
                    category_str = detection_data.get("category", "")
                    confidence = float(detection_data.get("confidence", 0.8))
                    reason = detection_data.get("reason", "AI Detection")
                    start_pos = int(detection_data.get("start_pos", 0))
                    end_pos = int(detection_data.get("end_pos", len(text)))
                    
                    # Map category string to enum
                    category = self._map_category_string(category_str)
                    
                    # Verify text exists in original and get accurate positions
                    actual_text, actual_start, actual_end = self._find_text_in_original(
                        text, original_text, start_pos, end_pos
                    )
                    
                    if actual_text:
                        # Get better context
                        context_start = max(0, actual_start - 75)
                        context_end = min(len(original_text), actual_end + 75)
                        context = original_text[context_start:context_end]
                        
                        detection = DetectionResult(
                            text=actual_text,
                            category=category,
                            confidence=min(confidence, 0.98),  # Cap confidence
                            page_number=page_num,
                            start_pos=actual_start,
                            end_pos=actual_end,
                            detection_reason=f"AI Detection: {reason}",
                            pattern_name="claude_ai",
                            context=context
                        )
                        detections.append(detection)
                        
                except (ValueError, KeyError, TypeError) as e:
                    logger.warning(f"Invalid detection data from Claude: {e}")
                    continue
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Claude response as JSON: {e}")
            logger.debug(f"Raw response: {response_text}")
        except Exception as e:
            logger.error(f"Error processing Claude response: {e}")
        
        return detections
    
    def _map_category_string(self, category_str: str) -> OPRACategory:
        """Map category string to OPRACategory enum"""
        # Direct mapping
        for category in OPRACategory:
            if category.value == category_str:
                return category
        
        # Fallback mappings
        category_lower = category_str.lower()
        if "personal" in category_lower or "identifying" in category_lower or "20" in category_str:
            return OPRACategory.PERSONAL_IDENTIFYING
        elif "criminal" in category_lower or "investigat" in category_lower or "5" in category_str:
            return OPRACategory.CRIMINAL_INVESTIGATORY
        elif "hipaa" in category_lower or "medical" in category_lower or "28" in category_str:
            return OPRACategory.HIPAA_DATA
        elif "attorney" in category_lower or "client" in category_lower or "9" in category_str:
            return OPRACategory.ATTORNEY_CLIENT
        elif "juvenile" in category_lower or "minor" in category_lower or "23" in category_str:
            return OPRACategory.JUVENILE_INFO
        
        # Default fallback
        return OPRACategory.PRIVACY_INTEREST
    
    def _find_text_in_original(self, target_text: str, original_text: str, 
                              suggested_start: int, suggested_end: int) -> tuple:
        """Find exact text match in original document"""
        
        # Try exact match first
        exact_pos = original_text.find(target_text)
        if exact_pos != -1:
            return target_text, exact_pos, exact_pos + len(target_text)
        
        # Try case insensitive
        exact_pos = original_text.lower().find(target_text.lower())
        if exact_pos != -1:
            actual_text = original_text[exact_pos:exact_pos + len(target_text)]
            return actual_text, exact_pos, exact_pos + len(target_text)
        
        # Try around suggested position with some tolerance
        search_start = max(0, suggested_start - 100)
        search_end = min(len(original_text), suggested_end + 100)
        search_area = original_text[search_start:search_end]
        
        # Look for partial matches
        words = target_text.split()
        if len(words) > 1:
            # Try to find the first few words
            for i in range(1, min(len(words) + 1, 4)):
                partial = " ".join(words[:i])
                pos = search_area.lower().find(partial.lower())
                if pos != -1:
                    actual_pos = search_start + pos
                    actual_text = original_text[actual_pos:actual_pos + len(partial)]
                    return actual_text, actual_pos, actual_pos + len(partial)
        
        return None, 0, 0

# Initialize detector
detector = AdvancedClaudeDetector()

@app.get("/")
async def root():
    return {
        "message": "OpenRecord API v2.0 with Claude AI",
        "status": "running",
        "ai_enabled": True
    }

@app.get("/health")
async def health_check():
    # Test Claude API connection
    claude_status = "healthy"
    try:
        test_response = await asyncio.to_thread(
            claude_client.messages.create,
            model="claude-3-sonnet-20240229",
            max_tokens=10,
            messages=[{"role": "user", "content": "Test"}]
        )
        claude_status = "healthy"
    except Exception as e:
        logger.error(f"Claude health check failed: {e}")
        claude_status = "unhealthy"
    
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "claude_ai": claude_status,
        "detection_engines": {
            "ai_detection": claude_status == "healthy",
            "pattern_detection": True,
            "context_analysis": True
        }
    }

@app.post("/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    
    # Generate unique document ID
    doc_id = str(uuid.uuid4())
    
    # Read file content
    content = await file.read()
    
    try:
        # Extract metadata using PyMuPDF
        doc = fitz.open(stream=content, filetype="pdf")
        metadata = {
            "page_count": len(doc),
            "title": doc.metadata.get("title", ""),
            "author": doc.metadata.get("author", ""),
            "creator": doc.metadata.get("creator", ""),
            "creation_date": doc.metadata.get("creationDate", ""),
        }
        doc.close()
        
        # Store document
        document_store[doc_id] = {
            "id": doc_id,
            "filename": file.filename,
            "content": content,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "size": len(content),
            "metadata": metadata
        }
        
        logger.info(f"Document uploaded: {file.filename} ({len(content)} bytes, {metadata['page_count']} pages)")
        
        return {
            "document_id": doc_id,
            "filename": file.filename,
            "size": len(content),
            "metadata": metadata
        }
        
    except Exception as e:
        logger.error(f"Error processing uploaded document: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing document: {str(e)}")

@app.post("/documents/{document_id}/analyze")
async def analyze_document(document_id: str, config: RedactionConfig):
    if document_id not in document_store:
        raise HTTPException(status_code=404, detail="Document not found")
    
    document = document_store[document_id]
    start_time = datetime.now()
    
    logger.info(f"Starting analysis of document {document_id} with config: {config.dict()}")
    
    try:
        # Process PDF
        doc = fitz.open(stream=document["content"], filetype="pdf")
        all_detections = []
        
        # Process each page
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            text = page.get_text()
            
            if not text.strip():
                continue
            
            page_detections = []
            
            # AI Detection with Claude (primary method)
            if config.use_ai_detection:
                try:
                    ai_detections = await detector.detect_with_claude(
                        text, page_num, config.document_type
                    )
                    page_detections.extend(ai_detections)
                except Exception as e:
                    logger.error(f"AI detection failed for page {page_num}: {e}")
            
            # Pattern Detection (backup/supplement)
            if config.use_pattern_detection:
                pattern_detections = detector.detect_with_patterns(text, page_num)
                page_detections.extend(pattern_detections)
            
            # Filter by enabled categories
            if config.enabled_categories:
                page_detections = [
                    d for d in page_detections 
                    if d.category in config.enabled_categories
                ]
            
            # Filter by confidence threshold
            page_detections = [
                d for d in page_detections 
                if d.confidence >= config.confidence_threshold
            ]
            
            all_detections.extend(page_detections)
            logger.info(f"Page {page_num}: found {len(page_detections)} detections")
        
        doc.close()
        
        # Remove duplicates and overlaps
        all_detections = remove_duplicate_detections(all_detections)
        
        # Calculate statistics
        processing_time = (datetime.now() - start_time).total_seconds()
        
        categories_found = list(set([d.category for d in all_detections]))
        pages_with_detections = list(set([d.page_number for d in all_detections]))
        
        # Confidence distribution
        confidence_dist = {"low": 0, "medium": 0, "high": 0}
        for d in all_detections:
            if d.confidence < 0.6:
                confidence_dist["low"] += 1
            elif d.confidence < 0.8:
                confidence_dist["medium"] += 1
            else:
                confidence_dist["high"] += 1
        
        statistics = AnalysisStatistics(
            total_detections=len(all_detections),
            high_confidence_count=len([d for d in all_detections if d.confidence > 0.8]),
            categories_found=categories_found,
            pages_with_detections=pages_with_detections,
            processing_time=processing_time
        )
        
        # Create analysis record
        analysis_id = str(uuid.uuid4())
        analysis = {
            "id": analysis_id,
            "document_id": document_id,
            "total_detections": len(all_detections),
            "high_confidence_count": statistics.high_confidence_count,
            "categories": [cat.value for cat in categories_found],
            "detections": [d.dict() for d in all_detections],
            "statistics": statistics.dict(),
            "processing_time": processing_time,
            "config_used": config.dict(),
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        analysis_store[analysis_id] = analysis
        
        logger.info(f"Analysis completed: {len(all_detections)} detections in {processing_time:.2f}s")
        
        return analysis
        
    except Exception as e:
        logger.error(f"Error analyzing document {document_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error analyzing document: {str(e)}")

@app.post("/documents/{document_id}/redact")
async def apply_redactions(document_id: str, redactions: List[Dict[str, Any]]):
    if document_id not in document_store:
        raise HTTPException(status_code=404, detail="Document not found")
    
    document = document_store[document_id]
    approved_redactions = [r for r in redactions if r.get("approved", True)]
    
    if not approved_redactions:
        raise HTTPException(status_code=400, detail="No approved redactions to apply")
    
    logger.info(f"Applying {len(approved_redactions)} redactions to document {document_id}")
    
    try:
        # Apply redactions using PyMuPDF
        doc = fitz.open(stream=document["content"], filetype="pdf")
        
        # Group redactions by page
        redactions_by_page = {}
        for redaction in approved_redactions:
            page_num = redaction["page_number"]
            if page_num not in redactions_by_page:
                redactions_by_page[page_num] = []
            redactions_by_page[page_num].append(redaction)
        
        # Apply redactions page by page
        for page_num, page_redactions in redactions_by_page.items():
            if page_num >= len(doc):
                continue
            
            page = doc.load_page(page_num)
            
            for redaction in page_redactions:
                # Find text instances on page
                text_instances = page.search_for(redaction["text"])
                
                if not text_instances:
                    # Try case-insensitive search
                    all_text = page.get_text()
                    text_lower = redaction["text"].lower()
                    idx = all_text.lower().find(text_lower)
                    if idx != -1:
                        # Create approximate rectangle
                        # This is a simplified approach - in production you'd want more precise positioning
                        rect = fitz.Rect(50, 50 + idx * 0.1, 200, 70 + idx * 0.1)
                        text_instances = [rect]
                
                for rect in text_instances:
                    # Create redaction annotation
                    redact_annot = page.add_redact_annot(rect)
                    category = redaction.get("category", "REDACTED")
                    redact_annot.set_info(content=f"[REDACTED-{category}]")
                    redact_annot.update()
            
            # Apply all redactions on this page
            page.apply_redactions()
        
        # Save redacted PDF
        pdf_bytes = doc.tobytes()
        doc.close()
        
        logger.info(f"Successfully applied redactions to document {document_id}")
        
        return StreamingResponse(
            BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=redacted_{document['filename']}"}
        )
        
    except Exception as e:
        logger.error(f"Error applying redactions: {e}")
        raise HTTPException(status_code=500, detail=f"Error applying redactions: {str(e)}")

@app.get("/documents")
async def list_documents():
    documents = []
    for doc_id, doc_data in document_store.items():
        documents.append({
            "id": doc_id,
            "filename": doc_data["filename"],
            "uploaded_at": doc_data["uploaded_at"],
            "size": doc_data["size"],
            "page_count": doc_data["metadata"]["page_count"]
        })
    return {"documents": documents}

@app.get("/config/patterns")
async def get_available_patterns():
    return {
        "patterns": {
            name: {
                "description": name.replace("_", " ").title(),
                "category": info["category"].value,
                "confidence": info["confidence"]
            }
            for name, info in detector.patterns.items()
        },
        "categories": {
            category.value: {
                "name": info["name"],
                "description": info["description"],
                "examples": info["examples"]
            }
            for category, info in OPRA_CATEGORIES.items()
        },
        "document_types": [
            "general", "police_report", "court_document", 
            "personnel_record", "medical_record", "legal_document"
        ]
    }

@app.delete("/documents/{document_id}")
async def delete_document(document_id: str):
    if document_id not in document_store:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Remove document
    del document_store[document_id]
    
    # Remove associated analyses
    analysis_ids_to_remove = [
        aid for aid, analysis in analysis_store.items()
        if analysis.get("document_id") == document_id
    ]
    
    for aid in analysis_ids_to_remove:
        del analysis_store[aid]
    
    logger.info(f"Deleted document {document_id} and {len(analysis_ids_to_remove)} associated analyses")
    
    return {"message": f"Document {document_id} deleted successfully"}

def remove_duplicate_detections(detections: List[DetectionResult]) -> List[DetectionResult]:
    """Remove duplicate and overlapping detections"""
    if not detections:
        return detections
    
    # Sort by page and position
    detections.sort(key=lambda x: (x.page_number, x.start_pos))
    
    deduplicated = []
    
    for current in detections:
        overlaps = False
        
        for i, existing in enumerate(deduplicated):
            if (current.page_number == existing.page_number and
                current.start_pos < existing.end_pos and
                current.end_pos > existing.start_pos):
                
                # Keep the one with higher confidence
                if current.confidence > existing.confidence:
                    deduplicated[i] = current
                overlaps = True
                break
        
        if not overlaps:
            deduplicated.append(current)
    
    return deduplicated

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app, 
        host=os.getenv("HOST", "0.0.0.0"), 
        port=int(os.getenv("PORT", 8000)),
        log_level="info"
    )