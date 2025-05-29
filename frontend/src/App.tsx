import React, { useState, useCallback, ChangeEvent, useEffect } from 'react';
import { 
  Upload, 
  FileText, 
  Download, 
  Check, 
  X, 
  Eye, 
  ChevronLeft, 
  ChevronRight,
  AlertCircle,
  CheckCircle,
  Clock,
  RefreshCw,
  ZoomIn,
  ZoomOut,
  RotateCw
} from 'lucide-react';
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
  const [error, setError] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  // State for view mode - change to table-based review
  const [viewMode, setViewMode] = useState<'preview' | 'review'>('preview');
  const [pageText, setPageText] = useState<{[key: number]: string}>({});

  // Load page text for text view
  const loadPageText = useCallback(async (docId: string, pageNum: number) => {
    if (pageText[pageNum]) return;
    
    try {
      const response = await fetch(`${API_BASE}/document/${docId}/text/${pageNum}`);
      if (response.ok) {
        const data = await response.json();
        setPageText(prev => ({ ...prev, [pageNum]: data.text }));
      }
    } catch (error) {
      console.error(`Failed to load text for page ${pageNum}:`, error);
    }
  }, [pageText]);

  // State for images and their dimensions
  const [pageImages, setPageImages] = useState<{[key: number]: string}>({});
  const [imageDimensions, setImageDimensions] = useState<{[key: number]: {width: number, height: number}}>({});

  // Handle image load to get actual dimensions
  const handleImageLoad = useCallback((pageNum: number, event: React.SyntheticEvent<HTMLImageElement>) => {
    const img = event.target as HTMLImageElement;
    setImageDimensions((prev: {[key: number]: {width: number, height: number}}) => ({
      ...prev,
      [pageNum]: {
        width: img.naturalWidth,
        height: img.naturalHeight
      }
    }));
  }, []);

  // Load page images
  const loadPageImage = useCallback(async (docId: string, pageNum: number) => {
    if (pageImages[pageNum]) return; // Already loaded
    
    try {
      const response = await fetch(`${API_BASE}/document/${docId}/page/${pageNum}`);
      if (response.ok) {
        const blob = await response.blob();
        const imageUrl = URL.createObjectURL(blob);
        setPageImages((prev: {[key: number]: string}) => ({ ...prev, [pageNum]: imageUrl }));
      }
    } catch (error) {
      console.error(`Failed to load page ${pageNum}:`, error);
    }
  }, [pageImages]);

  // Preload adjacent pages for smooth navigation
  useEffect(() => {
    if (!analysis) return;
    
    const pagesToLoad = [
      currentPage - 1,
      currentPage,
      currentPage + 1
    ].filter(p => p >= 0 && p < analysis.total_pages);
    
    // Load images for preview mode
    pagesToLoad.forEach(pageNum => {
      loadPageImage(analysis.document_id, pageNum);
    });

    // Load text if needed (for future text-based features)
    if (viewMode === 'review') {
      pagesToLoad.forEach(pageNum => {
        loadPageText(analysis.document_id, pageNum);
      });
    }
  }, [analysis, currentPage, loadPageImage, loadPageText, viewMode]);

  const handleFileSelect = useCallback((event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file && file.type === 'application/pdf') {
      setSelectedFile(file);
      setAnalysis(null);
      setSelectedRedactions(new Set());
      setDownloadUrl(null);
      setError(null);
      setPageImages({});
    } else {
      setError('Please select a PDF file');
    }
  }, []);

  const handleUpload = async () => {
    if (!selectedFile) return;

    setIsUploading(true);
    setError(null);
    
    const formData = new FormData();
    formData.append('file', selectedFile);

    try {
      const response = await fetch(`${API_BASE}/upload`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Upload failed' }));
        throw new Error(errorData.detail || 'Upload failed');
      }

      const analysisResult: DocumentAnalysis = await response.json();
      setAnalysis(analysisResult);
      
      // Initially select all redactions
      const allRedactionIds = new Set(analysisResult.redactions.map((_, index) => index));
      setSelectedRedactions(allRedactionIds);
      
    } catch (error) {
      console.error('Upload error:', error);
      setError(error instanceof Error ? error.message : 'Upload failed. Please try again.');
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
    setError(null);

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
        throw new Error('Failed to generate redacted document');
      }

      const result = await response.json();
      setDownloadUrl(`${API_BASE}/download/${analysis.document_id}`);
      
    } catch (error) {
      console.error('Redaction error:', error);
      setError('Failed to generate redacted document. Please try again.');
    } finally {
      setIsGenerating(false);
    }
  };

  const getCategoryColor = (category: string): string => {
    const colors: { [key: string]: string } = {
      'REDACTED-N.J.S.A. 47:1A-1': '#ef4444',
      'REDACTED-N.J.S.A. 47:1A-1.1(2)': '#f97316',
      'REDACTED-N.J.S.A. 47:1A-1.1(5)': '#eab308',
      'REDACTED-N.J.S.A. 47:1A-1.1(6)': '#22c55e',
      'REDACTED-N.J.S.A. 47:1A-1.1(8)': '#06b6d4',
      'REDACTED-N.J.S.A. 47:1A-1.1(9)': '#3b82f6',
      'REDACTED-N.J.S.A. 47:1A-1.1(12)': '#8b5cf6',
      'REDACTED-N.J.S.A. 47:1A-1.1(15)': '#ec4899',
      'REDACTED-N.J.S.A. 47:1A-1.1(20)': '#dc2626',
      'REDACTED-N.J.S.A. 47:1A-1.1(23)': '#f59e0b',
      'REDACTED-N.J.S.A. 47:1A-1.1(28)': '#10b981',
      'REDACTED-N.J.S.A. 47:1A-10': '#6366f1',
    };
    return colors[category] || '#6b7280';
  };

  const getCategoryShortName = (category: string): string => {
    const shortNames: { [key: string]: string } = {
      'REDACTED-N.J.S.A. 47:1A-1': 'Privacy',
      'REDACTED-N.J.S.A. 47:1A-1.1(2)': 'Internal',
      'REDACTED-N.J.S.A. 47:1A-1.1(5)': 'Criminal',
      'REDACTED-N.J.S.A. 47:1A-1.1(6)': 'Victim',
      'REDACTED-N.J.S.A. 47:1A-1.1(8)': 'Trade Secret',
      'REDACTED-N.J.S.A. 47:1A-1.1(9)': 'Attorney-Client',
      'REDACTED-N.J.S.A. 47:1A-1.1(12)': 'Security',
      'REDACTED-N.J.S.A. 47:1A-1.1(15)': 'Employment',
      'REDACTED-N.J.S.A. 47:1A-1.1(20)': 'PII',
      'REDACTED-N.J.S.A. 47:1A-1.1(23)': 'Juvenile',
      'REDACTED-N.J.S.A. 47:1A-1.1(28)': 'HIPAA',
      'REDACTED-N.J.S.A. 47:1A-10': 'Personnel',
    };
    return shortNames[category] || 'Other';
  };

  const currentPageRedactions = analysis?.redactions.filter(r => r.page === currentPage) || [];

  const navigateToPage = (pageNum: number) => {
    if (analysis && pageNum >= 0 && pageNum < analysis.total_pages) {
      setCurrentPage(pageNum);
    }
  };

  const selectAllRedactions = () => {
    if (analysis) {
      setSelectedRedactions(new Set(analysis.redactions.map((_, i) => i)));
    }
  };

  const deselectAllRedactions = () => {
    setSelectedRedactions(new Set());
  };

  const togglePageRedactions = () => {
    if (!analysis) return;
    
    const pageRedactionIndices = analysis.redactions
      .map((r, index) => ({ redaction: r, index }))
      .filter(({ redaction }) => redaction.page === currentPage)
      .map(({ index }) => index);
    
    const pageRedactionsSelected = pageRedactionIndices.every(i => selectedRedactions.has(i));
    
    const newSelected = new Set(selectedRedactions);
    if (pageRedactionsSelected) {
      // Deselect all page redactions
      pageRedactionIndices.forEach(i => newSelected.delete(i));
    } else {
      // Select all page redactions
      pageRedactionIndices.forEach(i => newSelected.add(i));
    }
    
    setSelectedRedactions(newSelected);
  };

  // Render text with highlighted redactions
  const renderTextWithHighlights = (text: string, redactions: RedactionItem[]) => {
    if (!redactions.length) {
      return <div className="plain-text">{text}</div>;
    }

    // Create array of text segments with highlight info
    const segments: Array<{text: string, isRedacted: boolean, redactionIndex?: number}> = [];
    let currentIndex = 0;
    
    // Sort redactions by their appearance in text
    const sortedRedactions = redactions
      .map((r, idx) => ({ ...r, globalIndex: analysis?.redactions.indexOf(r) || idx }))
      .filter(r => text.includes(r.text))
      .sort((a, b) => {
        const aPos = text.indexOf(a.text);
        const bPos = text.indexOf(b.text);
        return aPos - bPos;
      });

    sortedRedactions.forEach((redaction) => {
      const startIndex = text.indexOf(redaction.text, currentIndex);
      if (startIndex >= 0) {
        // Add text before redaction
        if (startIndex > currentIndex) {
          segments.push({
            text: text.slice(currentIndex, startIndex),
            isRedacted: false
          });
        }
        
        // Add redacted text
        segments.push({
          text: redaction.text,
          isRedacted: true,
          redactionIndex: redaction.globalIndex
        });
        
        currentIndex = startIndex + redaction.text.length;
      }
    });
    
    // Add remaining text
    if (currentIndex < text.length) {
      segments.push({
        text: text.slice(currentIndex),
        isRedacted: false
      });
    }

    return (
      <div className="highlighted-text">
        {segments.map((segment, index) => 
          segment.isRedacted ? (
            <span
              key={index}
              className={`redacted-text ${selectedRedactions.has(segment.redactionIndex!) ? 'selected' : 'unselected'}`}
              style={{
                backgroundColor: selectedRedactions.has(segment.redactionIndex!) 
                  ? getCategoryColor(redactions.find(r => analysis?.redactions.indexOf(r) === segment.redactionIndex)?.category || '') + '60'
                  : '#f3f4f6',
                borderColor: getCategoryColor(redactions.find(r => analysis?.redactions.indexOf(r) === segment.redactionIndex)?.category || '')
              }}
              onClick={() => toggleRedaction(segment.redactionIndex!)}
              title={`Click to ${selectedRedactions.has(segment.redactionIndex!) ? 'exclude' : 'include'} this redaction`}
            >
              {segment.text}
            </span>
          ) : (
            <span key={index} className="normal-text">
              {segment.text}
            </span>
          )
        )}
      </div>
    );
  };

  // Get context around a redaction for the table view
  const getRedactionContext = (redaction: RedactionItem, analysis: DocumentAnalysis) => {
    // This would ideally come from the backend, but for now we'll create a simple context
    const contextLength = 40; // Characters before and after
    
    // Create a simple context based on the redaction text
    const before = `...${redaction.text.slice(0, 10)}`.padStart(contextLength, '.');
    const after = `${redaction.text.slice(-10)}...`.padEnd(contextLength, '.');
    
    return {
      before: before.slice(0, contextLength),
      after: after.slice(0, contextLength)
    };
  };

  return (
    <div className="app-container">
      <div className="max-width">
        <header className="header">
          <h1>NJ OPRA Document Redaction Service</h1>
          <p>Upload PDF documents for automated redaction analysis according to New Jersey Open Public Records Act</p>
        </header>

        {/* Error Display */}
        {error && (
          <div className="error-banner">
            <AlertCircle className="error-icon" />
            <span>{error}</span>
            <button onClick={() => setError(null)} className="error-close">
              <X className="icon" />
            </button>
          </div>
        )}

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
                <div className="document-controls">
                  <div className="view-mode-controls">
                    <button
                      onClick={() => setViewMode('preview')}
                      className={`view-mode-btn ${viewMode === 'preview' ? 'active' : ''}`}
                    >
                      <Eye className="icon-small" />
                      Preview
                    </button>
                    <button
                      onClick={() => setViewMode('review')}
                      className={`view-mode-btn ${viewMode === 'review' ? 'active' : ''}`}
                    >
                      <FileText className="icon-small" />
                      Review Table
                    </button>
                  </div>
                  
                  <div className="page-controls">
                    <button
                      onClick={() => navigateToPage(currentPage - 1)}
                      disabled={currentPage === 0}
                      className="btn-control"
                    >
                      <ChevronLeft className="icon" />
                    </button>
                    <span className="page-info">
                      Page {currentPage + 1} of {analysis.total_pages}
                    </span>
                    <button
                      onClick={() => navigateToPage(currentPage + 1)}
                      disabled={currentPage === analysis.total_pages - 1}
                      className="btn-control"
                    >
                      <ChevronRight className="icon" />
                    </button>
                  </div>
                  
                  {viewMode === 'preview' && (
                    <div className="zoom-controls">
                      <button
                        onClick={() => setZoom(Math.max(0.5, zoom - 0.1))}
                        className="btn-control"
                      >
                        <ZoomOut className="icon-small" />
                      </button>
                      <span className="zoom-info">{Math.round(zoom * 100)}%</span>
                      <button
                        onClick={() => setZoom(Math.min(2, zoom + 0.1))}
                        className="btn-control"
                      >
                        <ZoomIn className="icon-small" />
                      </button>
                    </div>
                  )}
                </div>
              </div>
              
              <div className="document-preview">
                {viewMode === 'preview' ? (
                  // PDF Preview (simplified - no overlays)
                  <div style={{ transform: `scale(${zoom})`, transformOrigin: 'top left' }}>
                    {pageImages[currentPage] ? (
                      <img
                        src={pageImages[currentPage]}
                        alt={`Page ${currentPage + 1}`}
                        className="document-image"
                        onLoad={(e) => handleImageLoad(currentPage, e)}
                      />
                    ) : (
                      <div className="loading-placeholder">
                        <RefreshCw className="spinner-icon" />
                        Loading page...
                      </div>
                    )}
                  </div>
                ) : (
                  // Redaction Review Table
                  <div className="redaction-review-table">
                    <div className="table-header">
                      <h3>Redaction Review - All Pages</h3>
                      <div className="table-summary">
                        <span>{selectedRedactions.size} of {analysis.redactions.length} redactions selected</span>
                        <div className="table-actions">
                          <button onClick={selectAllRedactions} className="btn btn-secondary btn-small">
                            Select All
                          </button>
                          <button onClick={deselectAllRedactions} className="btn btn-secondary btn-small">
                            Deselect All
                          </button>
                        </div>
                      </div>
                    </div>
                    
                    <div className="redaction-table-container">
                      <table className="redaction-table">
                        <thead>
                          <tr>
                            <th>Include</th>
                            <th>Page</th>
                            <th>Sensitive Information</th>
                            <th>Context</th>
                            <th>Category</th>
                            <th>Confidence</th>
                          </tr>
                        </thead>
                        <tbody>
                          {analysis.redactions.map((redaction, index) => {
                            const isSelected = selectedRedactions.has(index);
                            const context = getRedactionContext(redaction, analysis);
                            
                            return (
                              <tr 
                                key={index} 
                                className={`redaction-row ${isSelected ? 'selected' : 'unselected'}`}
                                onClick={() => toggleRedaction(index)}
                              >
                                <td className="checkbox-cell">
                                  <input
                                    type="checkbox"
                                    checked={isSelected}
                                    onChange={() => toggleRedaction(index)}
                                    className="redaction-checkbox"
                                  />
                                </td>
                                <td className="page-cell">
                                  <button
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      setViewMode('preview');
                                      navigateToPage(redaction.page);
                                    }}
                                    className="page-link"
                                  >
                                    {redaction.page + 1}
                                  </button>
                                </td>
                                <td className="redaction-cell">
                                  <span className="redacted-value">
                                    "{redaction.text}"
                                  </span>
                                </td>
                                <td className="context-cell">
                                  <span className="context-text">
                                    {context.before}
                                    <mark className="highlighted-redaction" style={{
                                      backgroundColor: getCategoryColor(redaction.category) + '40',
                                      borderColor: getCategoryColor(redaction.category)
                                    }}>
                                      {redaction.text}
                                    </mark>
                                    {context.after}
                                  </span>
                                </td>
                                <td className="category-cell">
                                  <span
                                    className="category-tag"
                                    style={{ backgroundColor: getCategoryColor(redaction.category) }}
                                  >
                                    {getCategoryShortName(redaction.category)}
                                  </span>
                                </td>
                                <td className="confidence-cell">
                                  <div className="confidence-bar">
                                    <div 
                                      className="confidence-fill"
                                      style={{ 
                                        width: `${redaction.confidence * 100}%`,
                                        backgroundColor: redaction.confidence > 0.8 ? '#10b981' : 
                                                         redaction.confidence > 0.6 ? '#f59e0b' : '#ef4444'
                                      }}
                                    />
                                    <span className="confidence-text">
                                      {Math.round(redaction.confidence * 100)}%
                                    </span>
                                  </div>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
              
              {/* Page Navigation */}
              <div className="page-navigation">
                <div className="page-thumbnails">
                  {Array.from({ length: Math.min(analysis.total_pages, 10) }, (_, i) => (
                    <button
                      key={i}
                      onClick={() => navigateToPage(i)}
                      className={`page-thumb ${i === currentPage ? 'active' : ''}`}
                    >
                      {i + 1}
                    </button>
                  ))}
                  {analysis.total_pages > 10 && <span>...</span>}
                </div>
                
                <div className="page-actions">
                  <button onClick={togglePageRedactions} className="btn btn-secondary">
                    Toggle Page Redactions
                  </button>
                </div>
              </div>
            </div>

            {/* Redaction List */}
            <div className="redaction-section">
              <div className="section-header">
                <h2>Proposed Redactions</h2>
                <div className="redaction-stats">
                  <span className="redaction-count">
                    {selectedRedactions.size} of {analysis.redactions.length} selected
                  </span>
                  <span className="page-redaction-count">
                    {currentPageRedactions.length} on current page
                  </span>
                </div>
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
                          <CheckCircle className="check-icon selected" />
                        ) : (
                          <X className="check-icon unselected" />
                        )}
                        <span
                          className="category-badge"
                          style={{ backgroundColor: getCategoryColor(redaction.category) }}
                        >
                          {getCategoryShortName(redaction.category)}
                        </span>
                        <span className="confidence-badge">
                          {Math.round(redaction.confidence * 100)}%
                        </span>
                      </div>
                      
                      <p className="redaction-text">
                        "{redaction.text}"
                      </p>
                      
                      <div className="redaction-meta">
                        <span>Page {redaction.page + 1}</span>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            navigateToPage(redaction.page);
                          }}
                          className="goto-page-btn"
                        >
                          Go to page
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
              
              <div className="action-buttons">
                <div className="selection-buttons">
                  <button
                    onClick={selectAllRedactions}
                    className="btn btn-secondary"
                  >
                    Select All
                  </button>
                  
                  <button
                    onClick={deselectAllRedactions}
                    className="btn btn-secondary"
                  >
                    Deselect All
                  </button>
                </div>
                
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
                    <>
                      <Download className="icon" />
                      Generate Redacted PDF ({selectedRedactions.size} redactions)
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Success Section */}
        {downloadUrl && (
          <div className="success-banner">
            <div className="success-content">
              <CheckCircle className="success-icon" />
              <div>
                <h3>Redacted Document Ready</h3>
                <p>Your document has been successfully redacted with {selectedRedactions.size} redactions applied.</p>
              </div>
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