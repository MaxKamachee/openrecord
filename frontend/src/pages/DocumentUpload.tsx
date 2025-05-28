import React, { useCallback, useState } from 'react';
import { useDropzone } from 'react-dropzone';
import { 
  CloudArrowUpIcon,
  DocumentTextIcon,
  CheckCircleIcon,
  XCircleIcon,
  PlayIcon
} from '@heroicons/react/24/outline';
import { useUploadDocument, useAnalyzeDocument } from '../services/api';
import { useStore } from '../store/useStore';
import toast from 'react-hot-toast';

interface UploadedFile {
  file: File;
  status: 'uploading' | 'success' | 'error';
  document_id?: string;
  error?: string;
}

const DocumentUpload: React.FC = () => {
  const uploadMutation = useUploadDocument();
  const analyzeMutation = useAnalyzeDocument();
  const { 
    redactionConfig, 
    setCurrentDocument, 
    setCurrentAnalysis, 
    addDocument, 
    addAnalysis 
  } = useStore();
  
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([]);

  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    const newFiles = acceptedFiles.map(file => ({ file, status: 'uploading' as const }));
    setUploadedFiles(prev => [...prev, ...newFiles]);

    for (let i = 0; i < acceptedFiles.length; i++) {
      const file = acceptedFiles[i];
      const fileIndex = uploadedFiles.length + i;

      try {
        const result = await uploadMutation.mutateAsync(file);

        setUploadedFiles(prev => 
          prev.map((f, idx) => 
            idx === fileIndex 
              ? { ...f, status: 'success', document_id: result.document_id }
              : f
          )
        );

        // Add to store
        const document = {
          id: result.document_id,
          filename: result.filename,
          size: result.size,
          page_count: Number(result.metadata.page_count) || 0,
          uploaded_at: new Date().toISOString(),
          metadata: {
            page_count: Number(result.metadata.page_count) || 0,
            content_type: typeof result.metadata.content_type === 'string' ? result.metadata.content_type : 'application/pdf',
            original_filename: result.filename,
            ...result.metadata
          } as const,
        } as const;
        
        addDocument(document);

      } catch (error) {
        setUploadedFiles(prev => 
          prev.map((f, idx) => 
            idx === fileIndex 
              ? { 
                  ...f, 
                  status: 'error',
                  error: error instanceof Error ? error.message : 'Upload failed'
                }
              : f
          )
        );
      }
    }
  }, [uploadMutation, uploadedFiles.length, addDocument]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'application/pdf': ['.pdf'] },
    maxSize: 50 * 1024 * 1024, // 50MB
    multiple: true,
  });

  const handleAnalyze = async (documentId: string) => {
    try {
      const analysis = await analyzeMutation.mutateAsync({
        documentId,
        config: redactionConfig
      });

      // Add analysis to store
      addAnalysis(analysis);
      setCurrentAnalysis(analysis);

      // Set current document
      const document = useStore.getState().documents.find(d => d.id === documentId);
      if (document) {
        setCurrentDocument(document);
      }

      toast.success('Analysis completed! Check the Review tab.');
    } catch (error) {
      console.error('Analysis failed:', error);
    }
  };

  const successfulUploads = uploadedFiles.filter(f => f.status === 'success');

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-gray-900">Upload Documents</h1>
        <p className="mt-2 text-gray-600">
          Upload PDF documents for AI-powered redaction analysis
        </p>
      </div>

      {/* Upload Area */}
      <div
        {...getRootProps()}
        className={`relative border-2 border-dashed rounded-lg p-12 text-center transition-colors duration-200 cursor-pointer ${
          isDragActive
            ? 'border-indigo-400 bg-indigo-50'
            : 'border-gray-300 hover:border-gray-400'
        }`}
      >
        <input {...getInputProps()} />
        
        <CloudArrowUpIcon className="mx-auto h-16 w-16 text-gray-400" />
        <h3 className="mt-4 text-xl font-medium text-gray-900">
          {isDragActive ? 'Drop files here' : 'Upload PDF documents'}
        </h3>
        <p className="mt-2 text-gray-600">
          Drag and drop files here, or click to select files
        </p>
        <p className="mt-1 text-sm text-gray-500">
          PDF files up to 50MB each
        </p>
      </div>
      {/* Upload Progress */}
      {uploadedFiles.length > 0 && (
        <div className="bg-white rounded-lg shadow">
          <div className="px-6 py-4 border-b border-gray-200">
            <h3 className="text-lg font-medium text-gray-900">Upload Progress</h3>
          </div>
          <div className="p-6 space-y-4">
            {uploadedFiles.map((uploadedFile, index) => (
              <div key={index} className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
                <div className="flex items-center">
                  <DocumentTextIcon className="h-8 w-8 text-gray-400 mr-3" />
                  <div>
                    <p className="text-sm font-medium text-gray-900">
                      {uploadedFile.file.name}
                    </p>
                    <p className="text-xs text-gray-500">
                      {(uploadedFile.file.size / 1024 / 1024).toFixed(2)} MB
                    </p>
                  </div>
                </div>

                <div className="flex items-center space-x-3">
                  {uploadedFile.status === 'uploading' && (
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-indigo-600" />
                  )}

                  {uploadedFile.status === 'success' && (
                    <>
                      <CheckCircleIcon className="h-5 w-5 text-green-500" />
                      <button
                        onClick={() => handleAnalyze(uploadedFile.document_id!)}
                        disabled={analyzeMutation.isPending}
                        className="inline-flex items-center px-3 py-1 border border-transparent text-xs font-medium rounded-md text-indigo-700 bg-indigo-100 hover:bg-indigo-200 disabled:opacity-50"
                      >
                        {analyzeMutation.isPending ? (
                          <div className="animate-spin rounded-full h-3 w-3 border-b-2 border-indigo-600 mr-1" />
                        ) : (
                          <PlayIcon className="mr-1 h-3 w-3" />
                        )}
                        Analyze
                      </button>
                    </>
                  )}

                  {uploadedFile.status === 'error' && (
                    <div className="flex items-center">
                      <XCircleIcon className="h-5 w-5 text-red-500" />
                      <span className="ml-2 text-xs text-red-600">
                        {uploadedFile.error}
                      </span>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Success Message */}
      {successfulUploads.length > 0 && (
        <div className="bg-green-50 rounded-lg p-6">
          <div className="flex items-center">
            <CheckCircleIcon className="h-6 w-6 text-green-500 mr-3" />
            <div>
              <h3 className="text-lg font-medium text-green-900">
                Upload Complete!
              </h3>
              <p className="text-sm text-green-700">
                {successfulUploads.length} document{successfulUploads.length !== 1 ? 's' : ''} uploaded successfully.
                Click "Analyze" to start AI redaction detection.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default DocumentUpload;