// src/App.tsx - Working version with regular CSS
import React, { useState, useCallback, ChangeEvent } from 'react';
import { Upload, FileText, Download, Check, X, Eye } from 'lucide-react';
import './App.css';

interface RedactionItem {
  page: number;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  category: string;
  text: string;
  confidence: number;
}

interface DocumentAnalysis {
  document_id: string;
  total_pages: number;
  redactions: RedactionItem[];
  status: string;
}

const API_BASE = 'http://localhost:8000';

const RedactionService = () => {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [analysis, setAnalysis] = useState<DocumentAnalysis | null>(null);
  const [selectedRedactions, setSelectedRedactions] = useState<Set<number>>(new Set());
  const [currentPage, setCurrentPage] = useState(0);
  const [isGenerating, setIsGenerating] = useState(false);
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);

  const handleFileSelect = useCallback((event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file && file.type === 'application/pdf') {
      setSelectedFile(file);
      setAnalysis(null);
      setSelectedRedactions(new Set());
      setDownloadUrl(null);
    } else {
      alert('Please select a PDF file');
    }
  }, []);

  const handleUpload = async () => {
    if (!selectedFile) return;

    setIsUploading(true);
    const formData = new FormData();
    formData.append('file', selectedFile);

    try {
      const response = await fetch(`${API_BASE}/upload`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        throw new Error('Upload failed');
      }

      const analysisResult: DocumentAnalysis = await response.json();
      setAnalysis(analysisResult);
      
      // Initially select all redactions
      const allRedactionIds = new Set(analysisResult.redactions.map((_, index) => index));
      setSelectedRedactions(allRedactionIds);
      
    } catch (error) {
      console.error('Upload error:', error);
      alert('Upload failed. Please try again.');
    } finally {
      setIsUploading(false);
    }
  };

  const toggleRedaction = (index: number) => {
    const newSelected = new Set(selectedRedactions);
    if (newSelected.has(index)) {
      newSelected.delete(index);
    } else {
      newSelected.add(index);
    }
    setSelectedRedactions(newSelected);
  };

  const handleGenerateRedacted = async () => {
    if (!analysis) return;

    setIsGenerating(true);

    try {
      // Update redactions based on user selection
      const finalRedactions = analysis.redactions.filter((_, index) => 
        selectedRedactions.has(index)
      );

      await fetch(`${API_BASE}/document/${analysis.document_id}/redactions`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ redactions: finalRedactions }),
      });

      // Generate redacted PDF
      const response = await fetch(`${API_BASE}/document/${analysis.document_id}/redact`, {
        method: 'POST',
      });

      if (!response.ok) {
        throw new Error('Redaction generation failed');
      }

      const result = await response.json();
      setDownloadUrl(`${API_BASE}/download/${analysis.document_id}`);
      
    } catch (error) {
      console.error('Redaction error:', error);
      alert('Failed to generate redacted document. Please try again.');
    } finally {
      setIsGenerating(false);
    }
  };

  const getCategoryColor = (category: string): string => {
    const colors: { [key: string]: string } = {
      'REDACTED-N.J.S.A. 47:1A-1': '#ff6b6b',
      'REDACTED-N.J.S.A. 47:1A-1.1(20)': '#ff8787',
      'REDACTED-N.J.S.A. 47:1A-1.1(23)': '#ffa8a8',
      'REDACTED-N.J.S.A. 47:1A-1.1(9)': '#4ecdc4',
      'REDACTED-N.J.S.A. 47:1A-1.1(28)': '#45b7d1',
      'REDACTED-N.J.S.A. 47:1A-1.1(5)': '#96ceb4',
      'REDACTED-N.J.S.A. 47:1A-1.1(8)': '#feca57',
      'REDACTED-N.J.S.A. 47:1A-10': '#ff9ff3',
    };
    return colors[category] || '#ddd';
  };

  const getCategoryShortName = (category: string): string => {
    const shortNames: { [key: string]: string } = {
      'REDACTED-N.J.S.A. 47:1A-1': 'Privacy',
      'REDACTED-N.J.S.A. 47:1A-1.1(20)': 'PII',
      'REDACTED-N.J.S.A. 47:1A-1.1(23)': 'Juvenile',
      'REDACTED-N.J.S.A. 47:1A-1.1(9)': 'Attorney-Client',
      'REDACTED-N.J.S.A. 47:1A-1.1(28)': 'HIPAA',
      'REDACTED-N.J.S.A. 47:1A-1.1(5)': 'Criminal Investigation',
      'REDACTED-N.J.S.A. 47:1A-1.1(8)': 'Trade Secrets',
      'REDACTED-N.J.S.A. 47:1A-10': 'Personnel',
    };
    return shortNames[category] || category.split('(')[1]?.replace(')', '') || 'Other';
  };

  const currentPageRedactions = analysis?.redactions.filter(r => r.page === currentPage) || [];

  return (
    <div className="app-container">
      <div className="max-width">
        <header className="header">
          <h1>NJ OPRA Document Redaction Service</h1>
          <p>Upload PDF documents for automated redaction analysis according to New Jersey Open Public Records Act</p>
        </header>

        {/* Upload Section */}
        {!analysis && (
          <div className="card">
            <h2>Upload Document</h2>
            
            <div className="upload-area">
              <FileText className="upload-icon" />
              
              <input
                type="file"
                accept=".pdf"
                onChange={handleFileSelect}
                className="hidden"
                id="file-upload"
              />
              
              <label htmlFor="file-upload" className="btn btn-primary">
                <Upload className="icon" />
                Select PDF File
              </label>
              
              {selectedFile && (
                <div className="file-selected">
                  <p>Selected: {selectedFile.name}</p>
                  
                  <button
                    onClick={handleUpload}
                    disabled={isUploading}
                    className={`btn btn-success ${isUploading ? 'btn-disabled' : ''}`}
                  >
                    {isUploading ? (
                      <>
                        <div className="spinner"></div>
                        Analyzing...
                      </>
                    ) : (
                      <>
                        <Eye className="icon" />
                        Analyze Document
                      </>
                    )}
                  </button>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Analysis Results */}
        {analysis && (
          <div className="analysis-grid">
            
            {/* Document Preview */}
            <div className="document-section">
              <div className="section-header">
                <h2>Document Preview</h2>
                <div className="page-controls">
                  <button
                    onClick={() => setCurrentPage(Math.max(0, currentPage - 1))}
                    disabled={currentPage === 0}
                    className="btn-small"
                  >
                    Previous
                  </button>
                  <span className="page-info">
                    Page {currentPage + 1} of {analysis.total_pages}
                  </span>
                  <button
                    onClick={() => setCurrentPage(Math.min(analysis.total_pages - 1, currentPage + 1))}
                    disabled={currentPage === analysis.total_pages - 1}
                    className="btn-small"
                  >
                    Next
                  </button>
                </div>
              </div>
              
              <div className="document-preview">
                <img
                  src={`${API_BASE}/document/${analysis.document_id}/page/${currentPage}`}
                  alt={`Page ${currentPage + 1}`}
                  className="document-image"
                />
                
                {/* Redaction Overlays */}
                {currentPageRedactions.map((redaction, index) => {
                  const globalIndex = analysis.redactions.indexOf(redaction);
                  const isSelected = selectedRedactions.has(globalIndex);
                  
                  return (
                    <div
                      key={index}
                      className={`redaction-overlay ${isSelected ? 'selected' : 'unselected'}`}
                      style={{
                        left: `${(redaction.x1 / 595) * 100}%`,
                        top: `${(redaction.y1 / 842) * 100}%`,
                        width: `${((redaction.x2 - redaction.x1) / 595) * 100}%`,
                        height: `${((redaction.y2 - redaction.y1) / 842) * 100}%`,
                      }}
                      onClick={() => toggleRedaction(globalIndex)}
                      title={`${redaction.text} (${getCategoryShortName(redaction.category)})`}
                    />
                  );
                })}
              </div>
            </div>

            {/* Redaction List */}
            <div className="redaction-section">
              <div className="section-header">
                <h2>Proposed Redactions</h2>
                <span className="redaction-count">
                  {selectedRedactions.size} of {analysis.redactions.length} selected
                </span>
              </div>
              
              <div className="redaction-list">
                {analysis.redactions.map((redaction, index) => (
                  <div
                    key={index}
                    className={`redaction-item ${selectedRedactions.has(index) ? 'item-selected' : 'item-unselected'}`}
                    onClick={() => toggleRedaction(index)}
                  >
                    <div className="redaction-content">
                      <div className="redaction-header">
                        {selectedRedactions.has(index) ? (
                          <Check className="check-icon selected" />
                        ) : (
                          <X className="check-icon unselected" />
                        )}
                        <span
                          className="category-badge"
                          style={{ backgroundColor: getCategoryColor(redaction.category) }}
                        >
                          {getCategoryShortName(redaction.category)}
                        </span>
                      </div>
                      
                      <p className="redaction-text">
                        "{redaction.text}"
                      </p>
                      
                      <div className="redaction-meta">
                        Page {redaction.page + 1} • Confidence: {Math.round(redaction.confidence * 100)}%
                      </div>
                    </div>
                  </div>
                ))}
              </div>
              
              <div className="action-buttons">
                <button
                  onClick={() => setSelectedRedactions(new Set(analysis.redactions.map((_, i) => i)))}
                  className="btn btn-secondary"
                >
                  Select All
                </button>
                
                <button
                  onClick={() => setSelectedRedactions(new Set())}
                  className="btn btn-secondary"
                >
                  Deselect All
                </button>
                
                <button
                  onClick={handleGenerateRedacted}
                  disabled={isGenerating || selectedRedactions.size === 0}
                  className={`btn btn-danger ${(isGenerating || selectedRedactions.size === 0) ? 'btn-disabled' : ''}`}
                >
                  {isGenerating ? (
                    <>
                      <div className="spinner white"></div>
                      Generating...
                    </>
                  ) : (
                    'Generate Redacted PDF'
                  )}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Download Section */}
        {downloadUrl && (
          <div className="success-banner">
            <div className="success-content">
              <h3>Redacted Document Ready</h3>
              <p>Your document has been successfully redacted and is ready for download.</p>
            </div>
            
            <a
              href={downloadUrl}
              className="btn btn-success"
              download
            >
              <Download className="icon" />
              Download PDF
            </a>
          </div>
        )}
      </div>
    </div>
  );
};

export default RedactionService;