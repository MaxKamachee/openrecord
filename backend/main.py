from fastapi import FastAPI, File, UploadFile, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
import fitz  # PyMuPDF
from pdf2image import convert_from_path
import anthropic
from anthropic import Anthropic, AsyncAnthropic
import asyncio
import json
import uuid
import os
from pathlib import Path
from typing import List, Dict, Any
from pydantic import BaseModel
import base64
import io
from PIL import Image
import tempfile
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()  # Load from .env file if it exists
except ImportError:
    pass  # dotenv not required in production

app = FastAPI(title="NJ OPRA Redaction Service")

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import the comprehensive detector
from anthropic import Anthropic, AsyncAnthropic

# Add after other imports
import sys
sys.path.append('.')  # Allow importing from current directory

# We'll implement the comprehensive detector inline for now
import re
from dataclasses import dataclass
from typing import List, Dict, Set, Tuple

@dataclass
class RedactionCandidate:
    text: str
    category: str
    confidence: float
    justification: str
    start_pos: int = 0
    end_pos: int = 0
    detection_method: str = "AI"

class ComprehensiveOPRADetector:
    """Multi-layered OPRA exemption detection system"""
    
    def __init__(self, anthropic_client: AsyncAnthropic):
        self.client = anthropic_client
        self.setup_patterns()
    
    def setup_patterns(self):
        """Define regex patterns for obvious PII"""
        self.patterns = {
            "ssn": {
                "pattern": r'\b\d{3}-\d{2}-\d{4}\b',
                "category": "REDACTED-N.J.S.A. 47:1A-1.1(20)",
                "confidence": 0.95
            },
            "phone": {
                "pattern": r'\b(?:\(\d{3}\)|\d{3})[- ]?\d{3}[- ]?\d{4}\b',
                "category": "REDACTED-N.J.S.A. 47:1A-1.1(20)",
                "confidence": 0.85
            },
            "email": {
                "pattern": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
                "category": "REDACTED-N.J.S.A. 47:1A-1.1(20)",
                "confidence": 0.80
            },
            "credit_card": {
                "pattern": r'\b(?:\d{4}[- ]?){3}\d{4}\b',
                "category": "REDACTED-N.J.S.A. 47:1A-1.1(20)",
                "confidence": 0.90
            }
        }
    
    async def detect_pattern_based(self, text: str) -> List[RedactionCandidate]:
        """Pattern-based detection for obvious PII"""
        candidates = []
        
        for pattern_name, pattern_info in self.patterns.items():
            matches = re.finditer(pattern_info["pattern"], text, re.IGNORECASE)
            for match in matches:
                candidates.append(RedactionCandidate(
                    text=match.group(),
                    category=pattern_info["category"],
                    confidence=pattern_info["confidence"],
                    justification=f"Pattern match: {pattern_name}",
                    start_pos=match.start(),
                    end_pos=match.end(),
                    detection_method="pattern"
                ))
        
        logger.info(f"Pattern-based detection found {len(candidates)} candidates")
        return candidates
    
    async def detect_ai_comprehensive(self, text: str) -> List[RedactionCandidate]:
        """Comprehensive AI analysis with full OPRA schema"""
        
        prompt = f"""
        You are a NJ OPRA compliance expert. Identify ALL information that must be redacted under New Jersey's Open Public Records Act.

        MANDATORY REDACTION CATEGORIES:
        
        ### PERSONAL INFORMATION (High Priority)
        - [REDACTED-N.J.S.A. 47:1A-1.1(20)]: SSNs, home addresses, phone numbers, birth dates, driver's licenses, credit cards, bank accounts, personal emails
        - [REDACTED-N.J.S.A. 47:1A-1]: Personal info with reasonable expectation of privacy
        - [REDACTED-N.J.S.A. 47:1A-1.1(23)]: Any information about persons under 18
        
        ### GOVERNMENT OPERATIONS
        - [REDACTED-N.J.S.A. 47:1A-1.1(2)]: Internal memos, deliberative materials, draft documents, policy discussions
        - [REDACTED-N.J.S.A. 47:1A-1.1(15)]: Harassment complaints, grievances, union negotiations
        - [REDACTED-N.J.S.A. 47:1A-10]: Employee evaluations, disciplinary records, salary details
        
        ### LAW ENFORCEMENT & SECURITY  
        - [REDACTED-N.J.S.A. 47:1A-1.1(5)]: Criminal investigation records, detective notes, surveillance
        - [REDACTED-N.J.S.A. 47:1A-1.1(6)]: Victim records, domestic violence, sexual assault info
        - [REDACTED-N.J.S.A. 47:1A-1.1(12)]: Security measures, undercover officers, patrol patterns
        - [REDACTED-N.J.S.A. 47:1A-3(a)]: Ongoing investigations
        
        ### LEGAL & CONFIDENTIAL
        - [REDACTED-N.J.S.A. 47:1A-1.1(9)]: Attorney-client privilege, legal advice, litigation strategy
        - [REDACTED-N.J.S.A. 47:1A-1.1(17)]: Court-ordered confidential info, sealed records
        
        ### MEDICAL & HEALTH
        - [REDACTED-N.J.S.A. 47:1A-1.1(28)]: HIPAA data, medical records, health insurance
        
        ### BUSINESS & TECHNICAL
        - [REDACTED-N.J.S.A. 47:1A-1.1(8)]: Trade secrets, proprietary info, pricing strategies
        - [REDACTED-N.J.S.A. 47:1A-1.1(10)]: Computer security, network diagrams, passwords
        
        TEXT TO ANALYZE:
        {text}

        SCAN FOR:
        1. Direct matches (SSNs, phone numbers, addresses)
        2. Context clues ("confidential", "internal", "privileged")
        3. Implied redactions (employee names in disciplinary context)
        4. Security-sensitive information
        5. Any information about minors

        Return JSON array ONLY - no other text:
        [
            {{
                "text": "exact text to redact",
                "category": "REDACTED-N.J.S.A. 47:1A-X.X(XX)",
                "confidence": 0.95,
                "justification": "specific reason"
            }}
        ]
        """
        
        try:
            response = await self.client.messages.create(
                model="claude-3-5-sonnet-latest",
                max_tokens=3000,
                messages=[{"role": "user", "content": prompt}]
            )
            
            response_text = response.content[0].text
            logger.info(f"AI comprehensive response: {response_text[:200]}...")
            
            candidates = []
            try:
                # Try direct JSON parse first
                results = json.loads(response_text)
                for result in results:
                    candidates.append(RedactionCandidate(
                        text=result["text"],
                        category=result["category"],
                        confidence=result["confidence"],
                        justification=result["justification"],
                        detection_method="AI"
                    ))
            except json.JSONDecodeError:
                # Extract JSON from response if wrapped in text
                json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
                if json_match:
                    try:
                        results = json.loads(json_match.group(0))
                        for result in results:
                            candidates.append(RedactionCandidate(
                                text=result["text"],
                                category=result["category"],
                                confidence=result["confidence"],
                                justification=result["justification"],
                                detection_method="AI"
                            ))
                    except:
                        logger.error(f"Failed to parse extracted JSON: {json_match.group(0)[:200]}")
            
            logger.info(f"AI comprehensive detection found {len(candidates)} candidates")
            return candidates
            
        except Exception as e:
            logger.error(f"AI comprehensive detection failed: {e}")
            return []
    
    def deduplicate_candidates(self, candidates: List[RedactionCandidate]) -> List[RedactionCandidate]:
        """Remove duplicates, keeping highest confidence version"""
        text_groups = {}
        for candidate in candidates:
            text_lower = candidate.text.lower().strip()
            if text_lower not in text_groups:
                text_groups[text_lower] = []
            text_groups[text_lower].append(candidate)
        
        deduplicated = []
        for text, group in text_groups.items():
            # Keep highest confidence candidate
            best = max(group, key=lambda x: x.confidence)
            deduplicated.append(best)
        
        logger.info(f"Deduplicated {len(candidates)} → {len(deduplicated)} candidates")
        return deduplicated
    
    def validate_coverage(self, candidates: List[RedactionCandidate]) -> Dict[str, int]:
        """Log coverage statistics"""
        categories_found = {}
        for candidate in candidates:
            category = candidate.category
            categories_found[category] = categories_found.get(category, 0) + 1
        
        logger.info("OPRA Category Coverage:")
        for category, count in sorted(categories_found.items()):
            logger.info(f"  {category}: {count} items")
        
        return categories_found
    
    async def analyze_comprehensive(self, text: str) -> List[RedactionCandidate]:
        """Main analysis method"""
        logger.info("Starting comprehensive OPRA analysis...")
        
        # Pass 1: Pattern-based detection
        pattern_candidates = await self.detect_pattern_based(text)
        
        # Pass 2: Comprehensive AI analysis  
        ai_candidates = await self.detect_ai_comprehensive(text)
        
        # Combine and deduplicate
        all_candidates = pattern_candidates + ai_candidates
        final_candidates = self.deduplicate_candidates(all_candidates)
        
        # Validate coverage
        coverage = self.validate_coverage(final_candidates)
        
        logger.info(f"Comprehensive analysis complete: {len(final_candidates)} final redaction candidates")
        
        return final_candidates

# Initialize Anthropic clients and comprehensive detector
try:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY environment variable not found!")
        client = None
        async_client = None
        comprehensive_detector = None
    else:
        client = Anthropic(api_key=api_key)  # For synchronous calls
        async_client = AsyncAnthropic(api_key=api_key)  # For async calls
        comprehensive_detector = ComprehensiveOPRADetector(async_client)
        logger.info("✅ Anthropic clients and comprehensive detector initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize Anthropic client: {e}")
    client = None
    async_client = None
    comprehensive_detector = None

# Data models
class RedactionItem(BaseModel):
    page: int
    x1: float
    y1: float
    x2: float
    y2: float
    category: str
    text: str
    confidence: float

class DocumentAnalysis(BaseModel):
    document_id: str
    total_pages: int
    redactions: List[RedactionItem]
    status: str

class RedactionUpdate(BaseModel):
    redactions: List[RedactionItem]

# Storage directories
UPLOAD_DIR = Path("uploads")
PROCESSED_DIR = Path("processed")
UPLOAD_DIR.mkdir(exist_ok=True)
PROCESSED_DIR.mkdir(exist_ok=True)

# NJ OPRA redaction categories for AI prompt
REDACTION_CATEGORIES = """
### [REDACTED-N.J.S.A. 47:1A-1]: Privacy Interest
- Citizen's personal information where disclosure would violate reasonable expectation of privacy
- Examples: Birth dates, Social Security numbers, home addresses, personal phone numbers, medical history details, family member names in sensitive contexts

### [REDACTED-N.J.S.A. 47:1A-1.1(20)]: Personal Identifying Information
- Social Security numbers, home addresses, credit/debit card numbers, bank account information, birth dates, personal email addresses, telephone numbers, driver's license numbers
- Examples: Employment applications with SSNs, credit card details, home addresses, license plates, drivers license numbers

### [REDACTED-N.J.S.A. 47:1A-1.1(23)]: Juvenile Information
- Personal identifying information of persons under 18, except for specific disclosures
- Examples: School records with student identifiers, juvenile offender information, youth program participation lists

### [REDACTED-N.J.S.A. 47:1A-1.1(9)]: Attorney-Client Privilege
- Records within the attorney-client privilege
- Examples: Legal advice memos, strategy discussions for litigation, settlement negotiations

### [REDACTED-N.J.S.A. 47:1A-1.1(28)]: HIPAA Data
- Data classified under HIPAA
- Examples: Patient medical records, health insurance claims, treatment authorization, prescription information

### [REDACTED-N.J.S.A. 47:1A-1.1(5)]: Criminal Investigatory Records
- Records pertaining to criminal investigations
- Examples: Detective notes, surveillance footage, confidential informant statements

### [REDACTED-N.J.S.A. 47:1A-1.1(8)]: Trade Secrets
- Trade secrets, proprietary commercial or financial information
- Examples: Chemical formulas, manufacturing processes, customer lists, pricing strategies

### [REDACTED-N.J.S.A. 47:1A-10]: Personnel and Pension Records
- Personnel and pension records, except for specific disclosed information
- Examples: Employee performance evaluations, salary details, disciplinary records
"""

async def analyze_text_with_ai(text: str) -> List[Dict]:
    """Analyze text content for redaction candidates using Anthropic API"""
    
    prompt = f"""
    You are an expert in New Jersey's Open Public Records Act (OPRA) redaction requirements. 
    Analyze the following text and identify information that should be redacted according to NJ OPRA exemptions.

    REDACTION CATEGORIES:
    {REDACTION_CATEGORIES}

    TEXT TO ANALYZE:
    {text}

    For each piece of information that should be redacted, provide:
    1. The exact text that should be redacted
    2. The specific NJ statute category (e.g., "REDACTED-N.J.S.A. 47:1A-1.1(20)")
    3. A confidence score (0.0-1.0)
    4. Brief justification

    Return your response as a JSON array with this structure:
    [
        {{
            "text": "exact text to redact",
            "category": "REDACTED-N.J.S.A. 47:1A-1.1(20)",
            "confidence": 0.95,
            "justification": "Contains Social Security number"
        }}
    ]

    Only identify information that clearly falls under NJ OPRA exemptions. Be conservative and precise.
    """

    try:
        logger.info(f"Analyzing text of length: {len(text)}")
        response = await client.messages.create(
            model="claude-3-sonnet-20240229",  # Use Claude 3 instead of Claude 4
            max_tokens=4000,
            messages=[{
                "role": "user",
                "content": prompt
            }]
        )
        
        # Parse the JSON response
        response_text = response.content[0].text
        logger.info(f"AI response: {response_text[:500]}...")  # Log first 500 chars
        
        # Try to extract JSON from response
        try:
            result = json.loads(response_text)
            logger.info(f"Successfully parsed {len(result)} redaction candidates")
            return result
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse as direct JSON, trying to extract from response")
            # If not valid JSON, try to extract JSON from markdown code blocks
            import re
            json_match = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', response_text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group(1))
                logger.info(f"Extracted JSON from markdown, found {len(result)} redaction candidates")
                return result
            else:
                logger.error(f"Could not parse AI response as JSON: {response_text}")
                # Let's also try to find any JSON array in the response
                json_array_match = re.search(r'\[.*?\]', response_text, re.DOTALL)
                if json_array_match:
                    try:
                        result = json.loads(json_array_match.group(0))
                        logger.info(f"Found JSON array in response, parsed {len(result)} redaction candidates")
                        return result
                    except:
                        pass
                return []
        
    except Exception as e:
        logger.error(f"AI analysis error: {e}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        return []

async def analyze_image_with_ai(image_data: bytes) -> List[Dict]:
    """Analyze image content for redaction candidates using Anthropic API"""
    
    if not client:
        logger.error("Anthropic client not initialized - check API key")
        return []
    
    # Convert image to base64
    image_base64 = base64.b64encode(image_data).decode()
    
    prompt = f"""
    You are an expert in New Jersey's Open Public Records Act (OPRA) redaction requirements.
    Analyze this image/PDF page and identify any text or information that should be redacted according to NJ OPRA exemptions.

    REDACTION CATEGORIES:
    {REDACTION_CATEGORIES}

    For each piece of information that should be redacted, provide:
    1. The exact text that should be redacted
    2. The specific NJ statute category
    3. A confidence score (0.0-1.0)
    4. Approximate location description (e.g., "top-left", "middle-right")

    Return your response as a JSON array with this structure:
    [
        {{
            "text": "exact text to redact",
            "category": "REDACTED-N.J.S.A. 47:1A-1.1(20)",
            "confidence": 0.95,
            "location": "top-left section"
        }}
    ]

    Only identify information that clearly falls under NJ OPRA exemptions. Be conservative and precise.
    """

    try:
        logger.info("Analyzing image with AI")
        response = await client.messages.create(
            model="claude-3-sonnet-20240229",  # Use Claude 3 instead of Claude 4
            max_tokens=4000,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt
                    },
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": image_base64
                        }
                    }
                ]
            }]
        )
        
        # Parse the JSON response
        response_text = response.content[0].text
        logger.info(f"AI image response: {response_text[:500]}...")
        
        try:
            result = json.loads(response_text)
            logger.info(f"Successfully parsed {len(result)} image redaction candidates")
            return result
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code blocks
            import re
            json_match = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', response_text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group(1))
                logger.info(f"Extracted JSON from image analysis, found {len(result)} redaction candidates")
                return result
            else:
                logger.error(f"Could not parse AI image response as JSON: {response_text}")
                return []
                
    except Exception as e:
        logger.error(f"AI image analysis error: {e}")
        return []

def extract_text_coordinates(pdf_path: str, text: str, page_num: int) -> Dict:
    """Find coordinates of specific text in PDF page"""
    doc = fitz.open(pdf_path)
    page = doc[page_num]
    
    # Search for the text
    text_instances = page.search_for(text)
    
    if text_instances:
        # Return the first instance coordinates
        rect = text_instances[0]
        return {
            "x1": rect.x0,
            "y1": rect.y0,
            "x2": rect.x1,
            "y2": rect.y1
        }
    else:
        # If exact text not found, return approximate coordinates
        # This is a fallback - in production you might want more sophisticated text matching
        return {
            "x1": 0,
            "y1": 0,
            "x2": 100,
            "y2": 20
        }

@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    """Upload and analyze a PDF document for redaction candidates"""
    
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    
    # Generate unique document ID
    doc_id = str(uuid.uuid4())
    logger.info(f"Processing document {doc_id}: {file.filename}")
    
    # Save uploaded file
    file_path = UPLOAD_DIR / f"{doc_id}.pdf"
    with open(file_path, "wb") as buffer:
        content = await file.read()
        buffer.write(content)
    
    logger.info(f"Saved file to {file_path}, size: {len(content)} bytes")
    
    try:
        # Open PDF and analyze
        doc = fitz.open(file_path)
        total_pages = len(doc)
        all_redactions = []
        
        logger.info(f"PDF has {total_pages} pages")
        
        for page_num in range(total_pages):
            logger.info(f"Processing page {page_num + 1}/{total_pages}")
            page = doc[page_num]
            
            # Extract text from page
            page_text = page.get_text()
            logger.info(f"Page {page_num + 1} text length: {len(page_text)}")
            
            # Convert page to image for AI analysis
            pix = page.get_pixmap()
            img_data = pix.tobytes("png")
            logger.info(f"Generated page image, size: {len(img_data)} bytes")
            
            # Analyze text content with comprehensive OPRA detection
            if page_text.strip():
                logger.info(f"Analyzing text content for page {page_num + 1} with comprehensive OPRA detection")
                text_redactions = await analyze_text_with_ai(page_text)
                logger.info(f"Comprehensive analysis found {len(text_redactions)} text-based redaction candidates")
                
                for redaction in text_redactions:
                    # Find coordinates for this text
                    coords = extract_text_coordinates(str(file_path), redaction["text"], page_num)
                    
                    all_redactions.append(RedactionItem(
                        page=page_num,
                        x1=coords["x1"],
                        y1=coords["y1"],
                        x2=coords["x2"],
                        y2=coords["y2"],
                        category=redaction["category"],
                        text=redaction["text"],
                        confidence=redaction["confidence"]
                    ))
            else:
                logger.info(f"Page {page_num + 1} has no extractable text")
            
            # Analyze image content with comprehensive OPRA detection
            logger.info(f"Analyzing image content for page {page_num + 1}")
            image_redactions = await analyze_image_with_ai(img_data)
            logger.info(f"Image analysis found {len(image_redactions)} image-based redaction candidates")
            
            for redaction in image_redactions:
                # For image-based redactions, estimate coordinates based on document structure
                # In production, you might use more sophisticated OCR coordinate detection
                all_redactions.append(RedactionItem(
                    page=page_num,
                    x1=50,  # Better placeholder coordinates
                    y1=50 + (len(all_redactions) * 25),  # Stagger vertically
                    x2=250,
                    y2=70 + (len(all_redactions) * 25),
                    category=redaction["category"],
                    text=redaction["text"],
                    confidence=redaction["confidence"]
                ))
        
        doc.close()
        
        logger.info(f"Total redaction candidates found: {len(all_redactions)}")
        
        # Store analysis results
        analysis = DocumentAnalysis(
            document_id=doc_id,
            total_pages=total_pages,
            redactions=all_redactions,
            status="analyzed"
        )
        
        # Save analysis to file (in production, use a database)
        analysis_path = PROCESSED_DIR / f"{doc_id}_analysis.json"
        with open(analysis_path, "w") as f:
            json.dump(analysis.dict(), f, indent=2)
        
        logger.info(f"Analysis complete for document {doc_id}")
        return analysis
        
    except Exception as e:
        logger.error(f"Analysis failed for document {doc_id}: {str(e)}")
        # Clean up on error
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

@app.get("/document/{doc_id}")
async def get_document_analysis(doc_id: str):
    """Get analysis results for a document"""
    
    analysis_path = PROCESSED_DIR / f"{doc_id}_analysis.json"
    
    if not analysis_path.exists():
        raise HTTPException(status_code=404, detail="Document not found")
    
    with open(analysis_path, "r") as f:
        analysis_data = json.load(f)
    
    return DocumentAnalysis(**analysis_data)

@app.put("/document/{doc_id}/redactions")
async def update_redactions(doc_id: str, updates: RedactionUpdate):
    """Update redaction selections after user review"""
    
    analysis_path = PROCESSED_DIR / f"{doc_id}_analysis.json"
    
    if not analysis_path.exists():
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Load existing analysis
    with open(analysis_path, "r") as f:
        analysis_data = json.load(f)
    
    # Update redactions
    analysis_data["redactions"] = [r.dict() for r in updates.redactions]
    analysis_data["status"] = "reviewed"
    
    # Save updated analysis
    with open(analysis_path, "w") as f:
        json.dump(analysis_data, f)
    
    return {"status": "updated"}

@app.post("/document/{doc_id}/redact")
async def generate_redacted_pdf(doc_id: str):
    """Generate final redacted PDF"""
    
    # Load analysis
    analysis_path = PROCESSED_DIR / f"{doc_id}_analysis.json"
    original_path = UPLOAD_DIR / f"{doc_id}.pdf"
    
    if not analysis_path.exists() or not original_path.exists():
        raise HTTPException(status_code=404, detail="Document not found")
    
    with open(analysis_path, "r") as f:
        analysis_data = json.load(f)
    
    try:
        # Open original PDF
        doc = fitz.open(original_path)
        
        # Apply redactions
        for redaction in analysis_data["redactions"]:
            page = doc[redaction["page"]]
            
            # Create redaction rectangle
            rect = fitz.Rect(
                redaction["x1"],
                redaction["y1"],
                redaction["x2"],
                redaction["y2"]
            )
            
            # Add redaction annotation
            annot = page.add_redact_annot(rect)
            annot.set_info(content=f"[{redaction['category']}]")
            annot.update()
        
        # Apply all redactions
        for page_num in range(len(doc)):
            doc[page_num].apply_redactions()
        
        # Save redacted PDF
        redacted_path = PROCESSED_DIR / f"{doc_id}_redacted.pdf"
        doc.save(redacted_path)
        doc.close()
        
        return {"status": "redacted", "download_url": f"/download/{doc_id}"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Redaction failed: {str(e)}")

@app.get("/download/{doc_id}")
async def download_redacted_pdf(doc_id: str):
    """Download the redacted PDF"""
    
    redacted_path = PROCESSED_DIR / f"{doc_id}_redacted.pdf"
    
    if not redacted_path.exists():
        raise HTTPException(status_code=404, detail="Redacted document not found")
    
    return FileResponse(
        redacted_path,
        media_type="application/pdf",
        filename=f"redacted_{doc_id}.pdf"
    )

@app.get("/document/{doc_id}/page/{page_num}")
async def get_page_image(doc_id: str, page_num: int):
    """Get a page as an image for frontend preview"""
    
    pdf_path = UPLOAD_DIR / f"{doc_id}.pdf"
    
    if not pdf_path.exists():
        logger.error(f"Document not found: {pdf_path}")
        raise HTTPException(status_code=404, detail="Document not found")
    
    try:
        logger.info(f"Generating page image for doc {doc_id}, page {page_num}")
        doc = fitz.open(pdf_path)
        
        if page_num >= len(doc) or page_num < 0:
            doc.close()
            raise HTTPException(status_code=400, detail="Invalid page number")
            
        page = doc[page_num]
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x zoom for better quality
        img_data = pix.tobytes("png")
        doc.close()
        
        logger.info(f"Generated page image, size: {len(img_data)} bytes")
        
        return Response(content=img_data, media_type="image/png")
        
    except Exception as e:
        logger.error(f"Failed to generate page image: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to generate page image: {str(e)}")

@app.get("/test")
async def test_endpoint():
    """Test endpoint to verify API is working"""
    return {
        "status": "API is working", 
        "anthropic_key_configured": bool(os.getenv("ANTHROPIC_API_KEY")),
        "clients_initialized": bool(async_client and client),
        "comprehensive_detector_ready": bool(comprehensive_detector)
    }

@app.post("/test-ai-comprehensive")
async def test_comprehensive_opra():
    """Test the comprehensive OPRA detection system"""
    # More complex sample text with multiple OPRA exemptions
    sample_text = """
    INTERNAL MEMO - CONFIDENTIAL
    
    Employee John Doe (SSN: 123-45-6789) was disciplined for policy violation.
    Home address: 456 Oak Street, Newark, NJ 07101
    Phone: (973) 555-0123
    Email: john.doe@gmail.com
    
    This matter is subject to attorney-client privilege as legal counsel advised on disciplinary procedures.
    
    Victim Sarah Johnson reported the incident (case #2024-001).
    Detective notes indicate ongoing investigation - surveillance footage shows suspect at location.
    
    Medical records from Dr. Smith's office show employee was treated for work-related injury.
    Insurance claim #789456 processed for $15,000.
    
    Security camera access code: 4821
    Network password: SecurePass123
    
    Minor involved: Student ID #12345 (age 16) witnessed incident.
    """
    
    try:
        if not comprehensive_detector:
            return {"error": "Comprehensive detector not initialized", "success": False}
        
        logger.info("Starting comprehensive OPRA test...")
        candidates = await comprehensive_detector.analyze_comprehensive(sample_text)
        
        # Convert to simple format for response
        results = []
        for candidate in candidates:
            results.append({
                "text": candidate.text,
                "category": candidate.category,
                "confidence": candidate.confidence,
                "justification": candidate.justification,
                "method": candidate.detection_method
            })
        
        # Count by category
        categories = {}
        for result in results:
            cat = result["category"]
            categories[cat] = categories.get(cat, 0) + 1
        
        return {
            "success": True,
            "sample_text": sample_text,
            "redactions_found": len(results),
            "redactions": results,
            "categories_detected": categories,
            "coverage_analysis": f"Found {len(categories)} different OPRA categories"
        }
        
    except Exception as e:
        logger.error(f"Comprehensive OPRA test failed: {e}")
        return {"error": str(e), "success": False}

@app.post("/test-ai")
async def test_ai_analysis():
    """Test AI analysis with sample text - now using comprehensive system"""
    sample_text = "John Doe lives at 123 Main Street, Anytown, NJ 07001. His Social Security number is 123-45-6789. Phone: (555) 123-4567."
    
    try:
        logger.info("Starting test AI analysis with comprehensive system...")
        logger.info(f"Sample text: {sample_text}")
        
        result = await analyze_text_with_ai(sample_text)
        
        logger.info(f"Test AI analysis complete, found {len(result)} redactions")
        for i, redaction in enumerate(result):
            logger.info(f"  Redaction {i+1}: {redaction}")
        
        return {"sample_text": sample_text, "redactions_found": len(result), "redactions": result}
    except Exception as e:
        logger.error(f"Test AI analysis failed: {e}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        return {"error": str(e), "sample_text": sample_text, "redactions_found": 0, "redactions": []}

@app.post("/debug-ai-chain")
async def debug_ai_chain():
    """Debug the AI analysis chain step by step"""
    sample_text = "John has SSN 123-45-6789 and lives at 456 Oak St."
    
    try:
        logger.info("=== DEBUG AI CHAIN ===")
        
        # Step 1: Check detector
        if not comprehensive_detector:
            return {"error": "Comprehensive detector not initialized", "step": "detector_check"}
        logger.info("✓ Comprehensive detector initialized")
        
        # Step 2: Test pattern detection
        pattern_candidates = await comprehensive_detector.detect_pattern_based(sample_text)
        logger.info(f"✓ Pattern detection found {len(pattern_candidates)} candidates")
        
        # Step 3: Test AI detection  
        ai_candidates = await comprehensive_detector.detect_ai_comprehensive(sample_text)
        logger.info(f"✓ AI detection found {len(ai_candidates)} candidates")
        
        # Step 4: Test full analysis
        full_result = await comprehensive_detector.analyze_comprehensive(sample_text)
        logger.info(f"✓ Full analysis found {len(full_result)} candidates")
        
        # Step 5: Test wrapper function
        wrapper_result = await analyze_text_with_ai(sample_text)
        logger.info(f"✓ Wrapper function found {len(wrapper_result)} candidates")
        
        return {
            "success": True,
            "sample_text": sample_text,
            "pattern_count": len(pattern_candidates),
            "ai_count": len(ai_candidates), 
            "full_count": len(full_result),
            "wrapper_count": len(wrapper_result),
            "wrapper_result": wrapper_result
        }
        
    except Exception as e:
        logger.error(f"Debug chain failed: {e}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        return {"error": str(e), "success": False}

@app.post("/test-ai-direct")
async def test_ai_direct():
    """Test direct AI call to debug API issues"""
    try:
        if not async_client:
            return {"error": "Anthropic async client not initialized - check API key", "success": False}
            
        logger.info("Testing direct AI call...")
        response = await async_client.messages.create(
            model="claude-3-5-sonnet-latest",
            max_tokens=1000,
            messages=[{
                "role": "user",
                "content": "Find any Social Security numbers in this text: John's SSN is 123-45-6789. Return only JSON array like: [{\"text\": \"123-45-6789\", \"type\": \"SSN\"}]"
            }]
        )
        
        # FIXED: Access response.content[0].text
        response_text = response.content[0].text
        logger.info(f"Direct AI response: {response_text}")
        
        return {
            "raw_response": response_text,
            "success": True
        }
    except Exception as e:
        logger.error(f"Direct AI test failed: {e}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        return {"error": str(e), "success": False}

@app.post("/debug-pdf-text")
async def debug_pdf_text(file: UploadFile = File(...)):
    """Debug PDF text extraction and analysis"""
    
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    
    doc_id = str(uuid.uuid4())[:8]  # Short ID for debugging
    
    try:
        # Save file temporarily
        file_path = UPLOAD_DIR / f"debug_{doc_id}.pdf"
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        logger.info(f"Debug: Saved PDF to {file_path}, size: {len(content)} bytes")
        
        # Extract text
        doc = fitz.open(file_path)
        page = doc[0]  # Just test first page
        page_text = page.get_text()
        doc.close()
        
        logger.info(f"Debug: Extracted text length: {len(page_text)}")
        logger.info(f"Debug: First 200 chars: {page_text[:200]}")
        
        if not page_text.strip():
            return {
                "error": "No text extracted from PDF",
                "text_length": len(page_text),
                "file_size": len(content)
            }
        
        # Test analysis
        redactions = await analyze_text_with_ai(page_text)
        
        # Cleanup
        file_path.unlink()
        
        return {
            "success": True,
            "text_length": len(page_text),
            "text_preview": page_text[:500],
            "redactions_found": len(redactions),
            "redactions": redactions
        }
        
    except Exception as e:
        logger.error(f"Debug PDF failed: {e}")
        return {"error": str(e), "success": False}

if __name__ == "__main__":
    import uvicorn
    
    # Set up logging to work with the startup script
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler()  # This will go to the startup.log via nohup
        ]
    )
    
    logger.info("=" * 50)
    logger.info("NJ OPRA Redaction Service - Backend Starting")
    logger.info("=" * 50)
    
    # Check environment
    if not os.getenv("ANTHROPIC_API_KEY"):
        logger.error("⚠️  ANTHROPIC_API_KEY not found in environment!")
        logger.error("   Create backend/.env file with: ANTHROPIC_API_KEY=your_key_here")
        logger.error("   Or export ANTHROPIC_API_KEY=your_key_here")
    else:
        logger.info("✅ ANTHROPIC_API_KEY configured")
    
    # Check directories
    UPLOAD_DIR.mkdir(exist_ok=True)
    PROCESSED_DIR.mkdir(exist_ok=True)
    logger.info("✅ Upload and processed directories ready")
    
    logger.info("🚀 Starting server on http://localhost:8000")
    logger.info("📚 API docs available at http://localhost:8000/docs")
    logger.info("🧪 Test endpoints: /test and /test-ai")
    
    try:
        uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
    except Exception as e:
        logger.error(f"❌ Failed to start server: {e}")