from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
import fitz  # PyMuPDF
import anthropic
from anthropic import AsyncAnthropic
import json
import uuid
import os
from pathlib import Path
from typing import List
from pydantic import BaseModel
import base64
import tempfile
import logging
import re

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = FastAPI(title="NJ OPRA Redaction Service")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Anthropic client
try:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY environment variable not found!")
        async_client = None
    else:
        async_client = AsyncAnthropic(api_key=api_key)
        logger.info("✅ Anthropic client initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize Anthropic client: {e}")
    async_client = None

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

# Comprehensive OPRA categories for AI analysis
OPRA_CATEGORIES = """
### [REDACTED-N.J.S.A. 47:1A-1]: Privacy Interest
- Citizen's personal information where disclosure would violate reasonable expectation of privacy
- Examples: Birth dates, Social Security numbers, home addresses, personal phone numbers, medical history details, family member names in sensitive contexts

### [REDACTED-N.J.S.A. 47:1A-1.1(2)]: Inter-agency or Intra-agency Material
- Advisory, consultative, or deliberative material, including draft documents
- Examples: Internal memos discussing policy options, preliminary drafts, emails between staff debating merits

### [REDACTED-N.J.S.A. 47:1A-1.1(5)]: Criminal Investigatory Records
- Records pertaining to criminal investigations
- Examples: Detective notes, surveillance footage, confidential informant statements, undercover operation details

### [REDACTED-N.J.S.A. 47:1A-1.1(6)]: Victims' Records
- Records held by victims' rights agencies
- Examples: Domestic violence shelter intake forms, sexual assault counseling notes, victim impact statements

### [REDACTED-N.J.S.A. 47:1A-1.1(8)]: Trade Secrets
- Trade secrets, proprietary commercial or financial information
- Examples: Chemical formulas, manufacturing processes, customer lists, pricing strategies

### [REDACTED-N.J.S.A. 47:1A-1.1(9)]: Attorney-Client Privilege
- Records within the attorney-client privilege
- Examples: Legal advice memos, strategy discussions for litigation, settlement negotiations

### [REDACTED-N.J.S.A. 47:1A-1.1(12)]: Security Measures
- Security measures and surveillance techniques that could risk safety if disclosed
- Examples: Undercover officer identities, surveillance equipment capabilities, patrol patterns

### [REDACTED-N.J.S.A. 47:1A-1.1(15)]: Employment-Related Complaints
- Sexual harassment complaints, grievances, collective negotiation documents
- Examples: Workplace harassment investigation files, union negotiation documents, employee grievances

### [REDACTED-N.J.S.A. 47:1A-1.1(20)]: Personal Identifying Information
- Social Security numbers, home addresses, credit/debit card numbers, bank account information, birth dates, personal email addresses, telephone numbers, driver's license numbers
- Examples: Employment applications with SSNs, credit card details, home addresses, license plates

### [REDACTED-N.J.S.A. 47:1A-1.1(23)]: Juvenile Information
- Personal identifying information of persons under 18
- Examples: School records with student identifiers, juvenile offender information, youth program participation

### [REDACTED-N.J.S.A. 47:1A-1.1(28)]: HIPAA Data
- Data classified under HIPAA
- Examples: Patient medical records, health insurance claims, treatment authorization, prescription information

### [REDACTED-N.J.S.A. 47:1A-10]: Personnel and Pension Records
- Personnel and pension records
- Examples: Employee performance evaluations, salary details, disciplinary records
"""

class OPRADetector:
    """Simplified, reliable OPRA detection system"""
    
    def __init__(self, anthropic_client: AsyncAnthropic):
        self.client = anthropic_client
        self.setup_patterns()
    
    def setup_patterns(self):
        """Define precise patterns that capture only the sensitive values, not labels"""
        self.patterns = {
            # Precise SSN - just the number
            "ssn": {
                "pattern": r'\b\d{3}-\d{2}-\d{4}\b',
                "category": "REDACTED-N.J.S.A. 47:1A-1.1(20)",
                "confidence": 0.98
            },
            # Phone numbers - just the number
            "phone": {
                "pattern": r'\b(?:\(\d{3}\)|\d{3})[- ]?\d{3}[- ]?\d{4}\b',
                "category": "REDACTED-N.J.S.A. 47:1A-1.1(20)",
                "confidence": 0.95
            },
            # Email addresses - just the email
            "email": {
                "pattern": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
                "category": "REDACTED-N.J.S.A. 47:1A-1.1(20)",
                "confidence": 0.95
            },
            # Employee ID - just the ID value after colon/space
            "employee_id_value": {
                "pattern": r'(?:Employee ID|EMP|ID)[:\s#]*\s*([A-Z0-9-]{3,15})\b',
                "category": "REDACTED-N.J.S.A. 47:1A-1.1(20)",
                "confidence": 0.90,
                "capture_group": 1  # Only capture the ID, not the label
            },
            # Birth date - just the date value
            "birth_date_value": {
                "pattern": r'(?:DOB|Date of Birth|Birth Date)[:\s]*\s*(\d{1,2}/\d{1,2}/\d{4})\b',
                "category": "REDACTED-N.J.S.A. 47:1A-1.1(20)",
                "confidence": 0.95,
                "capture_group": 1
            },
            # Standalone dates (be more conservative)
            "date_standalone": {
                "pattern": r'\b(?:0[1-9]|1[0-2])/(?:0[1-9]|[12][0-9]|3[01])/(?:19|20)\d{2}\b',
                "category": "REDACTED-N.J.S.A. 47:1A-1.1(20)",
                "confidence": 0.80
            },
            # Names - be more careful, look for proper name patterns
            "person_name": {
                "pattern": r'\b[A-Z][a-z]+\s+[A-Z]\.\s+[A-Z][a-z]+\b|\b[A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b',
                "category": "REDACTED-N.J.S.A. 47:1A-1.1(20)",
                "confidence": 0.85
            },
            # Address - just the street address part
            "street_address": {
                "pattern": r'\b\d+\s+[A-Z][A-Za-z\s]+(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln|Court|Ct|Place|Pl|Boulevard|Blvd)\b',
                "category": "REDACTED-N.J.S.A. 47:1A-1.1(20)",
                "confidence": 0.90
            },
            # Security codes - just the code value
            "security_code_value": {
                "pattern": r'(?:Security Code|Access Code|Code)[:\s]*\s*(\d{4,6})\b',
                "category": "REDACTED-N.J.S.A. 47:1A-1.1(12)",
                "confidence": 0.95,
                "capture_group": 1
            },
            # Building/room access codes - just the number
            "access_code": {
                "pattern": r'(?:Building|Room|Access)[:\s]*(?:Code|Key)[:\s]*\s*(\d{4,8})\b',
                "category": "REDACTED-N.J.S.A. 47:1A-1.1(12)",
                "confidence": 0.95,
                "capture_group": 1
            },
            # Passwords - just the password value
            "password_value": {
                "pattern": r'(?:Password|PWD|Pass)[:\s]*\s*([A-Za-z0-9!@#$%^&*]{6,25})\b',
                "category": "REDACTED-N.J.S.A. 47:1A-1.1(12)",
                "confidence": 0.95,
                "capture_group": 1
            },
            # CVV - just the number
            "cvv_value": {
                "pattern": r'(?:CVV|CVC)[:\s]*\s*(\d{3,4})\b',
                "category": "REDACTED-N.J.S.A. 47:1A-1.1(20)",
                "confidence": 0.95,
                "capture_group": 1
            },
            # Credit card numbers
            "credit_card": {
                "pattern": r'\b(?:\d{4}[- ]?){3}\d{4}\b',
                "category": "REDACTED-N.J.S.A. 47:1A-1.1(20)",
                "confidence": 0.95
            },
            # Dollar amounts - be selective about context
            "salary_amount": {
                "pattern": r'\$[\d,]+,?\d{3}(?:,\d{3})*(?:\.\d{2})?',
                "category": "REDACTED-N.J.S.A. 47:1A-10",
                "confidence": 0.85
            },
            # Zip codes (standalone)
            "zip_code": {
                "pattern": r'\b\d{5}(?:-\d{4})?\b',
                "category": "REDACTED-N.J.S.A. 47:1A-1.1(20)",
                "confidence": 0.75
            }
        }
    
    async def detect_pattern_based(self, text: str) -> List[dict]:
        """Pattern-based detection for precise PII values only"""
        candidates = []
        
        for pattern_name, pattern_info in self.patterns.items():
            matches = re.finditer(pattern_info["pattern"], text, re.IGNORECASE)
            for match in matches:
                
                # Check if we should use a capture group (for value-only patterns)
                if "capture_group" in pattern_info:
                    # Extract just the captured value (e.g., the ID number, not "Employee ID: 12345")
                    if match.group(pattern_info["capture_group"]):
                        redacted_text = match.group(pattern_info["capture_group"])
                        # Find the position of the captured group within the full match
                        full_match = match.group(0)
                        value_start_in_full = full_match.find(redacted_text)
                        actual_start = match.start() + value_start_in_full
                        actual_end = actual_start + len(redacted_text)
                    else:
                        continue  # Skip if capture group is empty
                else:
                    # Use the full match
                    redacted_text = match.group(0)
                    actual_start = match.start()
                    actual_end = match.end()
                
                candidates.append({
                    "text": redacted_text,
                    "category": pattern_info["category"],
                    "confidence": pattern_info["confidence"],
                    "justification": f"Pattern match: {pattern_name}",
                    "start_pos": actual_start,
                    "end_pos": actual_end,
                    "detection_method": "pattern"
                })
        
        logger.info(f"Pattern detection found {len(candidates)} precise candidates")
        return candidates
    
    async def detect_ai_based(self, text: str) -> List[dict]:
        """AI-based comprehensive OPRA detection with precise value extraction"""
        
        if not self.client:
            logger.error("Anthropic client not initialized")
            return []
        
        prompt = f"""
You are an expert in New Jersey's Open Public Records Act (OPRA). Analyze the following text and identify ONLY the sensitive VALUES that should be redacted, NOT the field labels.

CRITICAL INSTRUCTIONS:
- ONLY identify the sensitive VALUE, not the label
- For "Employee ID: EMP-12345" → identify "EMP-12345" only
- For "SSN: 123-45-6789" → identify "123-45-6789" only  
- For "DOB: 04/12/1975" → identify "04/12/1975" only
- For "Password: SecurePass123" → identify "SecurePass123" only
- For "John A. Smith" → identify the full name
- Be PRECISE - extract only the sensitive value, preserve field labels

OPRA EXEMPTION CATEGORIES:
{OPRA_CATEGORIES}

TEXT TO ANALYZE:
{text}

SEARCH FOR THESE VALUE TYPES:
1. Names (full names of people)
2. ID numbers (employee IDs, case numbers, etc.)
3. SSNs (social security numbers)
4. Birth dates (in MM/DD/YYYY format)
5. Phone numbers
6. Email addresses  
7. Street addresses
8. Security codes/passwords
9. Financial amounts
10. Access codes

Return ONLY a JSON array with this exact structure:
[
  {{
    "text": "exact sensitive value only",
    "category": "REDACTED-N.J.S.A. 47:1A-1.1(20)",
    "confidence": 0.95,
    "justification": "specific reason"
  }}
]

IMPORTANT: Extract ONLY the sensitive values, NOT the field labels!"""
        
        try:
            response = await self.client.messages.create(
                model="claude-3-5-sonnet-latest",
                max_tokens=4000,
                messages=[{"role": "user", "content": prompt}]
            )
            
            response_text = response.content[0].text
            logger.info(f"AI precise detection response length: {len(response_text)}")
            
            # Parse JSON response
            try:
                # Try direct parse first
                results = json.loads(response_text)
            except json.JSONDecodeError:
                # Extract JSON from markdown if needed
                json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
                if json_match:
                    results = json.loads(json_match.group(0))
                else:
                    logger.error("Could not parse AI response as JSON")
                    return []
            
            logger.info(f"AI precise detection found {len(results)} value-only candidates")
            return results
            
        except Exception as e:
            logger.error(f"AI precise detection failed: {e}")
            return []
    
    async def analyze_comprehensive(self, text: str) -> List[dict]:
        """Main analysis combining pattern and AI detection"""
        logger.info("Starting comprehensive OPRA analysis...")
        
        # Pattern-based detection
        pattern_results = await self.detect_pattern_based(text)
        
        # AI-based detection
        ai_results = await self.detect_ai_based(text)
        
        # Combine and deduplicate
        all_results = pattern_results + ai_results
        
        # Simple deduplication by text
        seen_texts = set()
        final_results = []
        for item in all_results:
            text_key = item["text"].lower().strip()
            if text_key not in seen_texts:
                seen_texts.add(text_key)
                final_results.append(item)
        
        logger.info(f"Final analysis: {len(final_results)} unique redaction candidates")
        return final_results

# Initialize detector
if async_client:
    detector = OPRADetector(async_client)
else:
    detector = None

def find_text_coordinates_precise(pdf_path: str, text: str, page_num: int) -> dict:
    """Enhanced coordinate detection with multiple fallback methods"""
    try:
        doc = fitz.open(pdf_path)
        page = doc[page_num]
        
        # Get page dimensions
        page_rect = page.rect
        page_width = page_rect.width
        page_height = page_rect.height
        
        logger.info(f"Finding coordinates for: '{text}' on page {page_num}")
        
        # Method 1: Exact text search
        search_variants = [
            text.strip(),
            text.replace('\n', ' ').strip(),
            ' '.join(text.split()),  # Normalize whitespace
        ]
        
        for variant in search_variants:
            if len(variant) >= 3:
                instances = page.search_for(variant)
                if instances:
                    rect = instances[0]
                    logger.info(f"Found exact match '{variant}' at ({rect.x0:.1f}, {rect.y0:.1f}, {rect.x1:.1f}, {rect.y1:.1f})")
                    doc.close()
                    return {
                        "x1": rect.x0,
                        "y1": rect.y0,
                        "x2": rect.x1,
                        "y2": rect.y1,
                        "method": "exact_match",
                        "confidence": 0.95
                    }
        
        # Method 2: Word-by-word search with context
        words = text.split()
        best_match = None
        best_confidence = 0
        
        for i, word in enumerate(words):
            if len(word) >= 3 and not word.isdigit():  # Skip short words and standalone numbers
                instances = page.search_for(word)
                if instances:
                    rect = instances[0]
                    
                    # Calculate confidence based on word importance
                    confidence = min(0.9, len(word) / 10 + 0.5)
                    
                    if confidence > best_confidence:
                        best_confidence = confidence
                        
                        # Estimate full phrase width
                        char_width = (rect.x1 - rect.x0) / len(word)
                        estimated_width = len(text) * char_width * 0.9
                        
                        best_match = {
                            "x1": rect.x0,
                            "y1": rect.y0,
                            "x2": min(rect.x0 + estimated_width, page_width - 5),
                            "y2": rect.y1,
                            "method": f"word_match_{word}",
                            "confidence": confidence
                        }
        
        if best_match:
            logger.info(f"Best word match: {best_match}")
            doc.close()
            return best_match
        
        # Method 3: Pattern-based coordinate detection for specific types
        if re.match(r'\d{3}-\d{2}-\d{4}', text):  # SSN
            ssn_instances = page.search_for(text)
            if ssn_instances:
                rect = ssn_instances[0]
                doc.close()
                return {
                    "x1": rect.x0,
                    "y1": rect.y0,
                    "x2": rect.x1,
                    "y2": rect.y1,
                    "method": "ssn_pattern",
                    "confidence": 0.98
                }
        
        # Method 4: Text structure analysis
        text_dict = page.get_text("dict")
        for block in text_dict.get("blocks", []):
            if "lines" in block:
                for line in block["lines"]:
                    line_text = ""
                    line_spans = []
                    
                    for span in line.get("spans", []):
                        span_text = span.get("text", "")
                        line_text += span_text
                        line_spans.append(span)
                    
                    # Check if target text appears in this line
                    if text.lower() in line_text.lower():
                        # Find the position within the line
                        text_start = line_text.lower().find(text.lower())
                        if text_start >= 0:
                            # Calculate character position within line
                            char_count = 0
                            target_span = None
                            span_offset = 0
                            
                            for span in line_spans:
                                span_text = span.get("text", "")
                                if char_count <= text_start < char_count + len(span_text):
                                    target_span = span
                                    span_offset = text_start - char_count
                                    break
                                char_count += len(span_text)
                            
                            if target_span:
                                bbox = target_span["bbox"]
                                
                                # Estimate position within span
                                span_width = bbox[2] - bbox[0]
                                span_text_len = len(target_span.get("text", ""))
                                if span_text_len > 0:
                                    char_width = span_width / span_text_len
                                    x_offset = span_offset * char_width
                                    text_width = len(text) * char_width
                                else:
                                    x_offset = 0
                                    text_width = span_width
                                
                                result = {
                                    "x1": bbox[0] + x_offset,
                                    "y1": bbox[1],
                                    "x2": min(bbox[0] + x_offset + text_width, page_width),
                                    "y2": bbox[3],
                                    "method": "text_analysis",
                                    "confidence": 0.80
                                }
                                
                                logger.info(f"Text analysis match: {result}")
                                doc.close()
                                return result
        
        doc.close()
        
        # Fallback: Intelligent positioning based on content type
        if re.match(r'\d{3}-\d{2}-\d{4}', text):  # SSN
            return {"x1": 200, "y1": 400, "x2": 300, "y2": 420, "method": "fallback_ssn", "confidence": 0.3}
        elif re.match(r'.+@.+\..+', text):  # Email
            return {"x1": 150, "y1": 350, "x2": 350, "y2": 370, "method": "fallback_email", "confidence": 0.3}
        elif re.match(r'^\d+\s+[A-Z]', text):  # Address
            return {"x1": 100, "y1": 500, "x2": 400, "y2": 520, "method": "fallback_address", "confidence": 0.3}
        else:
            # Generic fallback with text-based variation
            y_pos = 200 + (abs(hash(text)) % 20) * 30
            x_pos = 80 + (len(text) % 5) * 20
            width = min(len(text) * 8, 300)
            
            return {
                "x1": x_pos,
                "y1": y_pos,
                "x2": x_pos + width,
                "y2": y_pos + 18,
                "method": "fallback_generic",
                "confidence": 0.2
            }
            
    except Exception as e:
        logger.error(f"Enhanced coordinate detection failed for '{text}': {e}")
        return {
            "x1": 50, 
            "y1": 100, 
            "x2": 200, 
            "y2": 120,
            "method": "error_fallback",
            "confidence": 0.1
        }

@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    """Upload and analyze PDF document"""
    
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    
    if not detector:
        raise HTTPException(status_code=500, detail="AI detection service not available")
    
    # Generate document ID
    doc_id = str(uuid.uuid4())
    logger.info(f"Processing document {doc_id}: {file.filename}")
    
    # Save uploaded file
    file_path = UPLOAD_DIR / f"{doc_id}.pdf"
    with open(file_path, "wb") as buffer:
        content = await file.read()
        buffer.write(content)
    
    try:
        # Open and analyze PDF
        doc = fitz.open(file_path)
        total_pages = len(doc)
        all_redactions = []
        
        logger.info(f"Analyzing {total_pages} pages...")
        
        for page_num in range(total_pages):
            page = doc[page_num]
            page_text = page.get_text()
            
            if not page_text.strip():
                logger.info(f"Page {page_num + 1} has no text, skipping")
                continue
            
            logger.info(f"Analyzing page {page_num + 1}, text length: {len(page_text)}")
            
            # Analyze text with comprehensive detection
            redaction_candidates = await detector.analyze_comprehensive(page_text)
            
            # Convert to RedactionItem objects
            for candidate in redaction_candidates:
                coords = find_text_coordinates_precise(str(file_path), candidate["text"], page_num)
                
                all_redactions.append(RedactionItem(
                    page=page_num,
                    x1=coords["x1"],
                    y1=coords["y1"],
                    x2=coords["x2"],
                    y2=coords["y2"],
                    category=candidate["category"],
                    text=candidate["text"],
                    confidence=candidate["confidence"]
                ))
        
        doc.close()
        
        logger.info(f"Analysis complete: {len(all_redactions)} redaction candidates found")
        
        # Save analysis
        analysis = DocumentAnalysis(
            document_id=doc_id,
            total_pages=total_pages,
            redactions=all_redactions,
            status="analyzed"
        )
        
        analysis_path = PROCESSED_DIR / f"{doc_id}_analysis.json"
        with open(analysis_path, "w") as f:
            json.dump(analysis.dict(), f, indent=2)
        
        return analysis
        
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

@app.get("/document/{doc_id}")
async def get_document_analysis(doc_id: str):
    """Get analysis results"""
    analysis_path = PROCESSED_DIR / f"{doc_id}_analysis.json"
    
    if not analysis_path.exists():
        raise HTTPException(status_code=404, detail="Document not found")
    
    with open(analysis_path, "r") as f:
        analysis_data = json.load(f)
    
    return DocumentAnalysis(**analysis_data)

@app.put("/document/{doc_id}/redactions")
async def update_redactions(doc_id: str, updates: RedactionUpdate):
    """Update redaction selections"""
    analysis_path = PROCESSED_DIR / f"{doc_id}_analysis.json"
    
    if not analysis_path.exists():
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Load and update analysis
    with open(analysis_path, "r") as f:
        analysis_data = json.load(f)
    
    analysis_data["redactions"] = [r.dict() for r in updates.redactions]
    analysis_data["status"] = "reviewed"
    
    with open(analysis_path, "w") as f:
        json.dump(analysis_data, f, indent=2)
    
    return {"status": "updated"}

@app.post("/document/{doc_id}/redact")
async def generate_redacted_pdf(doc_id: str):
    """Generate final redacted PDF with black rectangles"""
    analysis_path = PROCESSED_DIR / f"{doc_id}_analysis.json"
    original_path = UPLOAD_DIR / f"{doc_id}.pdf"
    
    if not analysis_path.exists() or not original_path.exists():
        raise HTTPException(status_code=404, detail="Document not found")
    
    with open(analysis_path, "r") as f:
        analysis_data = json.load(f)
    
    try:
        # Apply redactions to PDF
        doc = fitz.open(original_path)
        
        for redaction in analysis_data["redactions"]:
            page = doc[redaction["page"]]
            
            rect = fitz.Rect(
                redaction["x1"],
                redaction["y1"],
                redaction["x2"],
                redaction["y2"]
            )
            
            # Add redaction annotation with black fill
            annot = page.add_redact_annot(rect)
            annot.set_info(content=f"[{redaction['category']}]")
            
            # Set redaction appearance to solid black
            annot.set_colors({"stroke": [0, 0, 0], "fill": [0, 0, 0]})
            annot.update()
        
        # Apply all redactions with black rectangles
        for page_num in range(len(doc)):
            doc[page_num].apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
        
        # Save redacted PDF
        redacted_path = PROCESSED_DIR / f"{doc_id}_redacted.pdf"
        doc.save(redacted_path)
        doc.close()
        
        return {"status": "redacted", "download_url": f"/download/{doc_id}"}
        
    except Exception as e:
        logger.error(f"Redaction failed: {e}")
        raise HTTPException(status_code=500, detail=f"Redaction failed: {str(e)}")

@app.get("/download/{doc_id}")
async def download_redacted_pdf(doc_id: str):
    """Download redacted PDF"""
    redacted_path = PROCESSED_DIR / f"{doc_id}_redacted.pdf"
    
    if not redacted_path.exists():
        raise HTTPException(status_code=404, detail="Redacted document not found")
    
    return FileResponse(
        redacted_path,
        media_type="application/pdf",
        filename=f"redacted_{doc_id}.pdf"
    )

@app.get("/document/{doc_id}/text/{page_num}")
async def get_page_text(doc_id: str, page_num: int):
    """Get page text for text view"""
    pdf_path = UPLOAD_DIR / f"{doc_id}.pdf"
    
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="Document not found")
    
    try:
        doc = fitz.open(pdf_path)
        
        if page_num >= len(doc) or page_num < 0:
            doc.close()
            raise HTTPException(status_code=400, detail="Invalid page number")
        
        page = doc[page_num]
        page_text = page.get_text()
        doc.close()
        
        return {"text": page_text, "page": page_num}
        
    except Exception as e:
        logger.error(f"Text extraction failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to extract text")

@app.get("/document/{doc_id}/page/{page_num}")
async def get_page_image(doc_id: str, page_num: int):
    """Get page as image for preview"""
    pdf_path = UPLOAD_DIR / f"{doc_id}.pdf"
    
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="Document not found")
    
    try:
        doc = fitz.open(pdf_path)
        
        if page_num >= len(doc) or page_num < 0:
            doc.close()
            raise HTTPException(status_code=400, detail="Invalid page number")
        
        page = doc[page_num]
        # Higher resolution for better quality
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        img_data = pix.tobytes("png")
        doc.close()
        
        return Response(content=img_data, media_type="image/png")
        
    except Exception as e:
        logger.error(f"Page image generation failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate page image")

@app.get("/test")
async def test_endpoint():
    """Test API functionality"""
    return {
        "status": "API is working",
        "anthropic_configured": bool(os.getenv("ANTHROPIC_API_KEY")),
        "client_ready": bool(async_client),
        "detector_ready": bool(detector)
    }

@app.post("/test-analysis")
async def test_analysis():
    """Test OPRA analysis with sample text"""
    sample_text = """
    JERMAINE D LEVY
    1703 73RD ST
    NORTH BERGEN, NJ 07047-3837
    Birth Date: 11/15/1985
    Drivers License No: L234135864118S2
    License Plate No: C56PLZ
    Telephone: (201) 555-0123
    
    Court ID: 2020, Prefix: E22, Ticket Number: 000375
    """
    
    if not detector:
        return {"error": "Detector not available", "success": False}
    
    try:
        results = await detector.analyze_comprehensive(sample_text)
        
        # Also test individual components
        pattern_results = await detector.detect_pattern_based(sample_text)
        ai_results = await detector.detect_ai_based(sample_text)
        
        return {
            "success": True,
            "sample_text": sample_text,
            "total_redactions": len(results),
            "pattern_redactions": len(pattern_results),
            "ai_redactions": len(ai_results),
            "redactions": results,
            "pattern_details": pattern_results,
            "ai_details": ai_results
        }
    except Exception as e:
        logger.error(f"Test analysis failed: {e}")
@app.post("/debug-coordinates")
async def debug_coordinates(file: UploadFile = File(...)):
    """Debug coordinate detection to see how text positions map to PDF coordinates"""
    
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    
    doc_id = str(uuid.uuid4())[:8]
    
    try:
        # Save file temporarily
        file_path = UPLOAD_DIR / f"debug_{doc_id}.pdf"
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        # Extract text and get coordinates for first page
        doc = fitz.open(file_path)
        page = doc[0]
        page_text = page.get_text()
        
        # Get page dimensions
        page_rect = page.rect
        page_info = {
            "width": page_rect.width,
            "height": page_rect.height
        }
        
        # Get text structure with coordinates
        text_dict = page.get_text("dict")
        text_blocks = []
        
        for block in text_dict.get("blocks", []):
            if "lines" in block:
                for line in block["lines"]:
                    for span in line.get("spans", []):
                        span_text = span.get("text", "").strip()
                        if span_text:
                            text_blocks.append({
                                "text": span_text,
                                "bbox": span["bbox"],
                                "font": span.get("font", ""),
                                "size": span.get("size", 0)
                            })
        
        doc.close()
        
        # Test coordinate detection for sample PII
        sample_texts = [
            "John Smith",
            "123-45-6789", 
            "(555) 123-4567",
            "john@email.com"
        ]
        
        coordinate_tests = []
        for sample_text in sample_texts:
            if sample_text.lower() in page_text.lower():
                coords = find_text_coordinates(str(file_path), sample_text, 0)
                coordinate_tests.append({
                    "text": sample_text,
                    "found_in_page": True,
                    "coordinates": coords
                })
        
        # Cleanup
        file_path.unlink()
        
        return {
            "success": True,
            "page_info": page_info,
            "text_blocks_count": len(text_blocks),
            "text_blocks": text_blocks[:20],  # First 20 for inspection
            "coordinate_tests": coordinate_tests,
            "instructions": {
                "page_dimensions": f"PDF page is {page_info['width']} x {page_info['height']} points",
                "coordinate_system": "PDF uses bottom-left origin, coordinates shown as (x1,y1,x2,y2)",
                "text_blocks": "Shows actual text spans with their bounding boxes"
            }
        }
        
    except Exception as e:
        logger.error(f"Debug coordinates failed: {e}")
@app.post("/quick-debug")
async def quick_debug(file: UploadFile = File(...)):
    """Quick debug for coordinate positioning issues"""
    
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    
    doc_id = str(uuid.uuid4())[:8]
    
    try:
        # Save file temporarily
        file_path = UPLOAD_DIR / f"debug_{doc_id}.pdf"
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        # Extract text from first page
        doc = fitz.open(file_path)
        page = doc[0]
        page_text = page.get_text()
        page_rect = page.rect
        
        logger.info(f"Debug: Page dimensions {page_rect.width} x {page_rect.height}")
        logger.info(f"Debug: Text length {len(page_text)}")
        
        # Find all names that look like "Employee ID:"
        import re
        names_found = []
        
        # Look for patterns like "Employee ID: 12345"
        employee_matches = re.finditer(r'Employee ID:\s*(\d+)', page_text, re.IGNORECASE)
        for match in employee_matches:
            full_match = match.group(0)
            coords = find_text_coordinates(str(file_path), full_match, 0)
            names_found.append({
                "text": full_match,
                "coordinates": coords,
                "pattern": "Employee ID"
            })
        
        # Look for email patterns
        email_matches = re.finditer(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', page_text)
        for match in email_matches:
            email = match.group(0)
            coords = find_text_coordinates(str(file_path), email, 0)
            names_found.append({
                "text": email,
                "coordinates": coords,
                "pattern": "Email"
            })
        
        # Look for phone patterns
        phone_matches = re.finditer(r'\b(?:\(\d{3}\)|\d{3})[- ]?\d{3}[- ]?\d{4}\b', page_text)
        for match in phone_matches:
            phone = match.group(0)
            coords = find_text_coordinates(str(file_path), phone, 0)
            names_found.append({
                "text": phone,
                "coordinates": coords,
                "pattern": "Phone"
            })
        
        # Look for names (capitalized words that appear to be names)
        name_matches = re.findall(r'\b[A-Z][a-z]+ [A-Z][a-z]+\b', page_text)
        for name in name_matches[:5]:  # First 5 names
            coords = find_text_coordinates(str(file_path), name, 0)
            names_found.append({
                "text": name,
                "coordinates": coords,
                "pattern": "Name"
            })
        
        doc.close()
        
        # Cleanup
        file_path.unlink()
        
        return {
            "success": True,
            "page_dimensions": {"width": page_rect.width, "height": page_rect.height},
            "extracted_text_preview": page_text[:500],  # First 500 chars
            "total_text_length": len(page_text),
            "items_found": len(names_found),
            "coordinate_mappings": names_found,
            "debug_info": {
                "pdf_coordinate_system": "Origin at bottom-left, y increases upward",
                "image_coordinate_system": "Origin at top-left, y increases downward",
                "scaling_needed": "PDF coordinates need to be scaled to match display image"
            }
        }
        
    except Exception as e:
        logger.error(f"Quick debug failed: {e}")
        return {"error": str(e), "success": False}

if __name__ == "__main__":
    import uvicorn
    
    logger.info("🚀 Starting NJ OPRA Redaction Service")
    logger.info("📋 API docs: http://localhost:8000/docs")
    logger.info("🧪 Test endpoint: http://localhost:8000/test")
    
    if not os.getenv("ANTHROPIC_API_KEY"):
        logger.error("⚠️ ANTHROPIC_API_KEY not set!")
        logger.error("Create backend/.env with: ANTHROPIC_API_KEY=your_key_here")
    
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")

@app.post("/debug-pdf-analysis")
async def debug_pdf_analysis(file: UploadFile = File(...)):
    """Debug PDF analysis to see what text is extracted and what redactions are found"""
    
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    
    if not detector:
        raise HTTPException(status_code=500, detail="Detector not available")
    
    doc_id = str(uuid.uuid4())[:8]
    
    try:
        # Save file temporarily
        file_path = UPLOAD_DIR / f"debug_{doc_id}.pdf"
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        # Extract text from first page
        doc = fitz.open(file_path)
        page = doc[0]
        page_text = page.get_text()
        
        # Get detailed text structure
        text_dict = page.get_text("dict")
        
        # Extract all text blocks for analysis
        all_text_blocks = []
        for block in text_dict.get("blocks", []):
            if "lines" in block:
                for line in block["lines"]:
                    for span in line.get("spans", []):
                        span_text = span.get("text", "").strip()
                        if span_text:
                            all_text_blocks.append({
                                "text": span_text,
                                "bbox": span["bbox"],
                                "font": span.get("font", ""),
                                "size": span.get("size", 0)
                            })
        
        doc.close()
        
        logger.info(f"Debug: Extracted text length: {len(page_text)}")
        
        if not page_text.strip():
            return {
                "error": "No text extracted from PDF",
                "text_length": len(page_text),
                "file_size": len(content)
            }
        
        # Test pattern detection
        pattern_results = await detector.detect_pattern_based(page_text)
        
        # Test AI detection
        ai_results = await detector.detect_ai_based(page_text)
        
        # Test comprehensive analysis
        comprehensive_results = await detector.analyze_comprehensive(page_text)
        
        # Cleanup
        file_path.unlink()
        
        return {
            "success": True,
            "extracted_text": page_text,
            "text_length": len(page_text),
            "text_blocks_count": len(all_text_blocks),
            "text_blocks": all_text_blocks[:10],  # First 10 blocks for review
            "pattern_redactions": len(pattern_results),
            "ai_redactions": len(ai_results),
            "comprehensive_redactions": len(comprehensive_results),
            "pattern_results": pattern_results,
            "ai_results": ai_results,
            "comprehensive_results": comprehensive_results
        }
        
    except Exception as e:
        logger.error(f"Debug PDF analysis failed: {e}")
        return {"error": str(e), "success": False}
    