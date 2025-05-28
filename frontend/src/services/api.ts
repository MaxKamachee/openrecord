import axios from 'axios';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { UseQueryResult, UseMutationResult } from '@tanstack/react-query';
import type { Document, Analysis, RedactionConfig, Detection } from '../store/useStore';
import toast from 'react-hot-toast';

// API Configuration
const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000,
});

// Response interfaces
interface HealthCheckResponse {
  status: string;
  timestamp: string;
}

interface UploadDocumentResponse {
  document_id: string;
  filename: string;
  size: number;
  metadata: Record<string, unknown>;
}

interface ListDocumentsResponse {
  documents: Document[];
}

interface PatternConfig {
  description: string;
  category: string;
  pattern: string;
  priority: number;
  enabled: boolean;
}

interface AvailablePatternsResponse {
  patterns: Record<string, PatternConfig>;
  categories: Record<string, string>;
  document_types: string[];
}

// API Functions
export class ApiService {
  static async healthCheck(): Promise<HealthCheckResponse> {
    const response = await api.get<HealthCheckResponse>('/health');
    return response.data;
  }

  static async uploadDocument(file: File): Promise<UploadDocumentResponse> {
    const formData = new FormData();
    formData.append('file', file);
    
    const response = await api.post<UploadDocumentResponse>(
      '/documents/upload', 
      formData, 
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
        timeout: 60000,
      }
    );
    
    return response.data;
  }

  static async listDocuments(): Promise<ListDocumentsResponse> {
    const response = await api.get<ListDocumentsResponse>('/documents');
    return response.data;
  }

  static async analyzeDocument(documentId: string, config: RedactionConfig): Promise<Analysis> {
    const response = await api.post<Analysis>(`/documents/${documentId}/analyze`, config);
    return response.data;
  }

  static async deleteDocument(documentId: string): Promise<{ success: boolean }> {
    const response = await api.delete(`/documents/${documentId}`);
    return response.data;
  }

  static async applyRedactions(documentId: string, redactions: Detection[]): Promise<Blob> {
    const response = await api.post<Blob>(
      `/documents/${documentId}/redact`, 
      redactions, 
      {
        responseType: 'blob',
        timeout: 120000,
      }
    );
    return response.data;
  }

  static async getAvailablePatterns(): Promise<AvailablePatternsResponse> {
    const response = await api.get<AvailablePatternsResponse>('/config/patterns');
    return response.data;
  }

  static async getDocumentUrl(documentId: string): Promise<string> {
    return `${API_BASE_URL}/documents/${documentId}`;
  }
}

// React Query Hooks
export const useHealthCheck = (): UseQueryResult<HealthCheckResponse, Error> => {
  return useQuery<HealthCheckResponse, Error>({
    queryKey: ['health'],
    queryFn: ApiService.healthCheck,
    refetchInterval: 5 * 60 * 1000, // 5 minutes
  });
};

export const useDocuments = (): UseQueryResult<ListDocumentsResponse, Error> => {
  return useQuery<ListDocumentsResponse, Error>({
    queryKey: ['documents'],
    queryFn: ApiService.listDocuments,
  });
};

export const useUploadDocument = (): UseMutationResult<
  UploadDocumentResponse, 
  Error, 
  File
> => {
  const queryClient = useQueryClient();
  
  return useMutation<UploadDocumentResponse, Error, File>({
    mutationFn: ApiService.uploadDocument,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documents'] });
      toast.success('Document uploaded successfully');
    },
    onError: (error: Error) => {
      toast.error(`Upload failed: ${error.message}`);
    },
  });
};

export const useAnalyzeDocument = (): UseMutationResult<
  Analysis, 
  Error, 
  { documentId: string; config: RedactionConfig }
> => {
  return useMutation<Analysis, Error, { documentId: string; config: RedactionConfig }>({
    mutationFn: ({ documentId, config }) => ApiService.analyzeDocument(documentId, config),
    onSuccess: (data) => {
      toast.success(`Analysis complete: ${data.total_detections} detections found`);
    },
    onError: (error: Error) => {
      toast.error(`Analysis failed: ${error.message}`);
    },
  });
};

interface ApplyRedactionsParams {
  documentId: string;
  redactions: Detection[];
}

export const useApplyRedactions = (): UseMutationResult<
  Blob, 
  Error, 
  ApplyRedactionsParams
> => {
  return useMutation<Blob, Error, ApplyRedactionsParams>({
    mutationFn: ({ documentId, redactions }) => 
      ApiService.applyRedactions(documentId, redactions),
    onSuccess: () => {
      toast.success('Redactions applied successfully');
    },
    onError: (error: Error) => {
      toast.error(`Redaction failed: ${error.message}`);
    },
  });
};

export const useAvailablePatterns = (): UseQueryResult<AvailablePatternsResponse, Error> => {
  return useQuery<AvailablePatternsResponse, Error>({
    queryKey: ['availablePatterns'],
    queryFn: ApiService.getAvailablePatterns,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
};

export const useDeleteDocument = () => {
  const queryClient = useQueryClient();
  
  return useMutation<{ success: boolean }, Error, string>({
    mutationFn: (documentId: string) => ApiService.deleteDocument(documentId),
    onSuccess: () => {
      // Invalidate and refetch documents query
      queryClient.invalidateQueries({ queryKey: ['documents'] });
      // Show success message
      toast.success('Document deleted successfully');
    },
    onError: (error: Error) => {
      toast.error(`Failed to delete document: ${error.message}`);
    },
  });
};