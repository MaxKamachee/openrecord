import React, { useEffect, useCallback, useRef } from 'react';
import { useParams } from 'react-router-dom';
import { 
  CheckIcon,
  XMarkIcon,
  DocumentArrowDownIcon,
  DocumentTextIcon,
  EyeIcon,
  InformationCircleIcon,
  ArrowPathIcon
} from '@heroicons/react/24/outline';
import { useApplyRedactions, useAnalyzeDocument } from '../services/api';
import { useStore } from '../store/useStore';
import type { Detection, Document, Analysis } from '../store/useStore';
import type { RedactionConfig } from '../store/useStore';
import { OPRACategory } from '../store/useStore';
import toast from 'react-hot-toast';

// Enhanced redaction config with maximum sensitivity
const defaultRedactionConfig: RedactionConfig = {
  document_type: 'general',
  confidence_threshold: 0.05, // Lower threshold to catch more potential PII
  use_ai_detection: true,
  use_pattern_detection: true,
  use_context_analysis: true,
  enabled_categories: [
    OPRACategory.PRIVACY_INTEREST,
    OPRACategory.PERSONAL_IDENTIFYING,
    OPRACategory.CRIMINAL_INVESTIGATORY,
    OPRACategory.HIPAA_DATA,
    OPRACategory.ATTORNEY_CLIENT,
    OPRACategory.JUVENILE_INFO
  ]
};

// Custom hook to handle document analysis
const useDocumentAnalysis = () => {
  const analyzeDocumentMutation = useAnalyzeDocument();
  const isAnalyzingRef = useRef(false);
  const { setCurrentAnalysis } = useStore();

  const startAnalysis = useCallback(async (docId: string) => {
    if (isAnalyzingRef.current) {
      console.log('Analysis already in progress, skipping...');
      return null;
    }

    try {
      isAnalyzingRef.current = true;
      console.log('Starting analysis for document:', docId);
      toast.loading('Starting analysis...', { id: 'analysis-status' });
      
      // Ensure we're sending the correct data structure
      const config = {
        document_type: defaultRedactionConfig.document_type,
        confidence_threshold: defaultRedactionConfig.confidence_threshold,
        enabled_categories: defaultRedactionConfig.enabled_categories,
        use_ai_detection: defaultRedactionConfig.use_ai_detection,
        use_pattern_detection: defaultRedactionConfig.use_pattern_detection,
        use_context_analysis: defaultRedactionConfig.use_context_analysis
      };
      
      console.log('Sending analysis request with config:', config);
      const result = await analyzeDocumentMutation.mutateAsync({
        documentId: docId,
        config: config
      });
      
      console.log('Analysis result:', result);
      
      // Define a partial detection type that matches our Detection interface
      type PartialDetection = Omit<Detection, 'id' | 'approved' | 'detection_reason' | 'page_number' | 'start_pos' | 'end_pos' | 'confidence'> & {
        id?: string;
        approved?: boolean;
        detection_reason?: string;
        page_number?: number;
        start_pos?: number;
        end_pos?: number;
        confidence?: number;
      };

      // Ensure the result has the expected structure
      const formattedResult = {
        ...result,
        // Make sure detections have all required fields
        detections: (result.detections || []).map((d: PartialDetection, index: number) => ({
          ...d,
          id: d.id || `detection-${index}-${Date.now()}`,
          approved: d.approved !== false, // Default to true if not specified
          detection_reason: d.detection_reason || 'Automatically detected',
          page_number: d.page_number || 0,
          start_pos: d.start_pos || 0,
          end_pos: d.end_pos || 0,
          confidence: d.confidence || 0.9
        }))
      };
      
      // Update the store with the analysis result
      setCurrentAnalysis(formattedResult);
      
      toast.success('Analysis completed!', { id: 'analysis-status' });
      return formattedResult;
    } catch (error) {
      console.error('Analysis failed:', error);
      toast.error(`Analysis failed: ${error instanceof Error ? error.message : 'Unknown error'}`, { 
        id: 'analysis-status',
        duration: 5000
      });
      throw error;
    } finally {
      isAnalyzingRef.current = false;
    }
  }, [analyzeDocumentMutation, setCurrentAnalysis]);

  return { 
    startAnalysis, 
    isAnalyzing: isAnalyzingRef.current
  };
};

const DocumentReview: React.FC = () => {
  const { documentId } = useParams<{ documentId: string }>();
  const { 
    currentDocument,
    currentAnalysis,
    updateDetection,
    approveAllDetections,
    rejectAllDetections,
    setCurrentDocument,
    setCurrentAnalysis,
    documents,
    analyses
  } = useStore();
  
  const applyRedactionsMutation = useApplyRedactions();
  const { startAnalysis, isAnalyzing } = useDocumentAnalysis();
  const hasStartedAnalysis = useRef(false);
  const isInitialLoad = useRef(true);

  // Load document and analysis when component mounts or documentId changes
  useEffect(() => {
    let isMounted = true;
    
    const loadDocumentAndAnalysis = async (documents: Document[], analyses: Record<string, Analysis>) => {
      if (!documentId) return;

      try {
        // Find the document in the store
        const document = documents.find(doc => doc.id === documentId);
        if (!document) {
          toast.error('Document not found');
          return;
        }
        
        // Update document if it's different
        if (currentDocument?.id !== document.id) {
          setCurrentDocument(document);
        }
        
        // Check if we already have an analysis for this document
        const existingAnalysis = Object.values(analyses).find(a => a.document_id === documentId);
        
        if (existingAnalysis) {
          // Only update if the analysis is different
          if (!currentAnalysis || currentAnalysis.id !== existingAnalysis.id) {
            setCurrentAnalysis(existingAnalysis);
          }
        } else if (isMounted && !isAnalyzing && !hasStartedAnalysis.current) {
          // Start analysis if no analysis exists and not already analyzing
          try {
            hasStartedAnalysis.current = true;
            const result = await startAnalysis(documentId);
            if (result && isMounted) {
              setCurrentAnalysis(result);
            }
          } catch (err) {
            console.error('Failed to analyze document:', err);
            toast.error('Failed to analyze document');
          } finally {
            if (isMounted) {
              hasStartedAnalysis.current = false;
            }
          }
        }
      } catch (err) {
        console.error('Error loading document:', err);
        toast.error('Error loading document');
      } finally {
        isInitialLoad.current = false;
      }
    };
    
    loadDocumentAndAnalysis(documents, analyses);
    
    return () => {
      isMounted = false;
    };
  }, [documentId, documents, analyses, startAnalysis, currentDocument?.id, currentAnalysis, isAnalyzing, setCurrentDocument, setCurrentAnalysis]);
  
  // Handle case when no document ID is provided
  if (!documentId) {
    return (
      <div className="text-center py-12">
        <DocumentTextIcon className="mx-auto h-12 w-12 text-gray-400" />
        <h3 className="mt-2 text-lg font-medium text-gray-900">No document selected</h3>
        <p className="mt-1 text-gray-500">Please select a document from the dashboard to review.</p>
      </div>
    );
  }

  // Show loading state while analyzing
  if (isAnalyzing) {
    return (
      <div className="flex flex-col items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mb-4"></div>
        <p className="text-gray-600">Analyzing document...</p>
        <p className="text-sm text-gray-500 mt-2">This may take a moment</p>
      </div>
    );
  }
  
  // Show error if analysis failed - we'll handle this through the toast notifications
  // since we're using react-hot-toast for error handling in the useDocumentAnalysis hook

  if (!currentDocument) {
    return (
      <div className="text-center py-12">
        <DocumentTextIcon className="mx-auto h-12 w-12 text-gray-400" />
        <h3 className="mt-2 text-lg font-medium text-gray-900">No document selected</h3>
        <p className="mt-1 text-gray-500">Please select a document from the dashboard to analyze.</p>
      </div>
    );
  }
  
  if (!currentAnalysis) {
    return (
      <div className="text-center py-12">
        <ArrowPathIcon className="mx-auto h-12 w-12 text-gray-400 animate-spin" />
        <h3 className="mt-2 text-lg font-medium text-gray-900">Preparing analysis</h3>
        <p className="mt-1 text-gray-500">Setting up the analysis for your document.</p>
      </div>
    );
  }

  // Get detections from current analysis or use empty array
  const detections = currentAnalysis?.detections || [];
  
  const approvedCount = detections.filter(d => d.approved).length;

  const handleApplyRedactions = async () => {
    if (!currentDocument || !currentAnalysis) {
      toast.error('No document or analysis available');
      return;
    }

    const approvedDetections = detections.filter(d => d.approved);
    
    if (approvedDetections.length === 0) {
      toast.error('No redactions approved');
      return;
    }

    try {
      const redactedPdf = await applyRedactionsMutation.mutateAsync({
        documentId: currentDocument.id,
        redactions: approvedDetections.map(d => ({
          ...d,
          detection_reason: d.detection_reason || 'Manually approved',
          id: d.id || `manual-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
          approved: true,
          pattern_name: d.pattern_name || '',
          context: d.context || ''
        }))
      });

      // Download the redacted PDF
      const url = window.URL.createObjectURL(redactedPdf);
      const a = document.createElement('a');
      a.style.display = 'none';
      a.href = url;
      a.download = `redacted_${currentDocument.filename}`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);

    } catch (error) {
      console.error('Error applying redactions:', error);
    }
  };

  if (!currentDocument || !currentAnalysis) {
    return (
      <div className="max-w-4xl mx-auto text-center py-12">
        <EyeIcon className="mx-auto h-16 w-16 text-gray-400 mb-4" />
        <h2 className="text-xl font-medium text-gray-900 mb-2">No Analysis Available</h2>
        <p className="text-gray-600 mb-6">Please upload and analyze a document first.</p>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto p-6">
      <div className="flex justify-between items-start mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Document Review</h1>
          <div className="mt-2 bg-blue-50 border-l-4 border-blue-400 p-4">
            <div className="flex">
              <div className="flex-shrink-0">
                <InformationCircleIcon className="h-5 w-5 text-blue-400" />
              </div>
              <div className="ml-3">
                <p className="text-sm text-blue-700">
                  All detections are automatically approved for maximum privacy protection. 
                  You can manually reject any false positives below.
                </p>
              </div>
            </div>
          </div>
        </div>
        <div className="flex space-x-3">
          <button
            onClick={handleApplyRedactions}
            disabled={approvedCount === 0}
            className={`inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white ${
              approvedCount === 0 ? 'bg-indigo-300' : 'bg-indigo-600 hover:bg-indigo-700'
            } focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500`}
          >
            <DocumentArrowDownIcon className="-ml-1 mr-2 h-5 w-5" />
            Apply {approvedCount} Redactions
          </button>
        </div>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-white rounded-lg shadow p-4">
          <div className="text-2xl font-bold text-gray-900">{detections.length}</div>
          <div className="text-sm text-gray-600">Total Detections</div>
        </div>
        <div className="bg-white rounded-lg shadow p-4">
          <div className="text-2xl font-bold text-green-600">{approvedCount}</div>
          <div className="text-sm text-gray-600">Approved</div>
        </div>
        <div className="bg-white rounded-lg shadow p-4">
          <div className="text-2xl font-bold text-red-600">{detections.length - approvedCount}</div>
          <div className="text-sm text-gray-600">Rejected</div>
        </div>
        <div className="bg-white rounded-lg shadow p-4">
          <div className="text-2xl font-bold text-blue-600">
            {detections.filter(d => d.confidence > 0.8).length}
          </div>
          <div className="text-sm text-gray-600">High Confidence</div>
        </div>
      </div>

      {/* Quick Actions */}
      <div className="bg-white rounded-lg shadow p-4">
        <h3 className="text-lg font-medium text-gray-900 mb-3">Quick Actions</h3>
        <div className="flex space-x-3">
          <button
            onClick={approveAllDetections}
            className="px-3 py-2 text-sm bg-green-100 text-green-800 rounded-md hover:bg-green-200"
          >
            ✅ Approve All
          </button>
          <button
            onClick={rejectAllDetections}
            className="px-3 py-2 text-sm bg-red-100 text-red-800 rounded-md hover:bg-red-200"
          >
            ❌ Reject All
          </button>
        </div>
      </div>

      {/* Detections Table */}
      <div className="bg-white shadow rounded-lg overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200">
          <h3 className="text-lg font-medium text-gray-900">
            Detected Redactions ({detections.length})
          </h3>
        </div>
        
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Text
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Category
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Page
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Confidence
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {detections.map((detection) => (
                <tr key={detection.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="max-w-xs">
                      <div className="font-mono text-sm bg-gray-100 px-2 py-1 rounded">
                        {detection.text.length > 50 
                          ? `${detection.text.substring(0, 50)}...` 
                          : detection.text
                        }
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-indigo-100 text-indigo-800">
                      {detection.category.split('.').pop()}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                    {detection.page_number + 1}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="flex items-center">
                      <div className="w-16 h-2 bg-gray-200 rounded-full mr-2">
                        <div 
                          className={`h-2 rounded-full ${
                            detection.confidence >= 0.8 ? 'bg-green-500' : 
                            detection.confidence >= 0.6 ? 'bg-yellow-500' : 'bg-red-500'
                          }`}
                          style={{ width: `${detection.confidence * 100}%` }}
                        />
                      </div>
                      <span className="text-sm font-medium">
                        {Math.round(detection.confidence * 100)}%
                      </span>
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="flex items-center space-x-2">
                      <button
                        onClick={() => updateDetection(detection.id, { approved: true })}
                        className={`p-1 rounded ${
                          detection.approved 
                            ? 'bg-green-100 text-green-600' 
                            : 'bg-gray-100 text-gray-400 hover:bg-green-100 hover:text-green-600'
                        }`}
                      >
                        <CheckIcon className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => updateDetection(detection.id, { approved: false })}
                        className={`p-1 rounded ${
                          !detection.approved 
                            ? 'bg-red-100 text-red-600' 
                            : 'bg-gray-100 text-gray-400 hover:bg-red-100 hover:text-red-600'
                        }`}
                      >
                        <XMarkIcon className="h-4 w-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Detection Details */}
      <div className="bg-gray-50 rounded-lg p-4">
        <h4 className="text-sm font-medium text-gray-900 mb-2">Detection Summary</h4>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <span className="text-gray-600">Analysis Time:</span>
            <span className="ml-2 font-medium text-gray-900">
              {currentAnalysis.processing_time.toFixed(1)}s
            </span>
          </div>
          <div>
            <span className="text-gray-600">Categories Found:</span>
            <span className="ml-2 font-medium text-gray-900">
              {currentAnalysis.categories.length}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DocumentReview;