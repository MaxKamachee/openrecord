import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { immer } from 'zustand/middleware/immer';

// Types
export interface Detection {
  text: string;
  category: string;
  confidence: number;
  page_number: number;
  start_pos: number;
  end_pos: number;
  detection_reason: string;
  pattern_name?: string;
  context?: string;
  approved: boolean;
  id: string;
}

export interface DocumentMetadata {
  page_count: number;
  content_type?: string;
  original_filename?: string;
  [key: string]: unknown;
}

export interface Document {
  id: string;
  filename: string;
  size: number;
  page_count: number;
  uploaded_at: string;
  metadata: DocumentMetadata;
}

export interface Analysis {
  id: string;
  document_id: string;
  total_detections: number;
  high_confidence_count: number;
  categories: string[];
  detections: Detection[];
  processing_time: number;
}

// OPRA Categories from the backend
export const OPRACategory = {
  PRIVACY_INTEREST: "N.J.S.A. 47:1A-1",
  PERSONAL_IDENTIFYING: "N.J.S.A. 47:1A-1.1(20)",
  CRIMINAL_INVESTIGATORY: "N.J.S.A. 47:1A-1.1(5)",
  HIPAA_DATA: "N.J.S.A. 47:1A-1.1(28)",
  ATTORNEY_CLIENT: "N.J.S.A. 47:1A-1.1(9)",
  JUVENILE_INFO: "N.J.S.A. 47:1A-1.1(23)"
} as const;

export type OPRACategory = typeof OPRACategory[keyof typeof OPRACategory];

export interface RedactionConfig {
  document_type: string;
  confidence_threshold: number;
  enabled_categories: OPRACategory[];
  use_ai_detection: boolean;
  use_pattern_detection: boolean;
  use_context_analysis: boolean;
  [key: string]: string | number | boolean | OPRACategory[] | undefined; // Allow additional properties with specific types
}

// Store interface
interface AppState {
  currentDocument: Document | null;
  currentAnalysis: Analysis | null;
  documents: Document[];
  analyses: Record<string, Analysis>;
  isLoading: boolean;
  error: string | null;
  redactionConfig: RedactionConfig;
}

interface AppActions {
  setCurrentDocument: (document: Document | null) => void;
  setCurrentAnalysis: (analysis: Analysis | null) => void;
  addDocument: (document: Document) => void;
  addAnalysis: (analysis: Analysis) => void;
  updateDetection: (detectionId: string, updates: Partial<Detection>) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  updateRedactionConfig: (config: Partial<RedactionConfig>) => void;
  approveAllDetections: () => void;
  rejectAllDetections: () => void;
}

// Default config with maximum accuracy settings
const defaultRedactionConfig: RedactionConfig = {
  document_type: 'general',
  confidence_threshold: 0.1, // Lower threshold to catch more potential PII
  enabled_categories: [
    OPRACategory.PRIVACY_INTEREST,
    OPRACategory.PERSONAL_IDENTIFYING,
    OPRACategory.CRIMINAL_INVESTIGATORY,
    OPRACategory.HIPAA_DATA,
    OPRACategory.ATTORNEY_CLIENT,
    OPRACategory.JUVENILE_INFO
  ],
  use_ai_detection: true,
  use_pattern_detection: true,
  use_context_analysis: true,
};

// Create store
// Persist configuration
const PERSIST_OPTIONS = {
  name: 'openrecord-storage',
  storage: createJSONStorage(() => localStorage),
  partialize: (state: AppState) => ({
    redactionConfig: state.redactionConfig,
    documents: state.documents,
    analyses: state.analyses,
  }),
};

export const useStore = create<AppState & AppActions>()(
  persist(
    immer((set) => ({
    // Initial state
    currentDocument: null,
    currentAnalysis: null,
    documents: [],
    analyses: {},
    isLoading: false,
    error: null,
    redactionConfig: defaultRedactionConfig,

    // Actions
    setCurrentDocument: (document) =>
      set((state) => {
        state.currentDocument = document;
      }),

    setCurrentAnalysis: (analysis) =>
      set((state) => {
        state.currentAnalysis = analysis;
      }),

    addDocument: (document) =>
      set((state) => {
        const existingIndex = state.documents.findIndex(d => d.id === document.id);
        if (existingIndex >= 0) {
          state.documents[existingIndex] = document;
        } else {
          state.documents.push(document);
        }
      }),

    addAnalysis: (analysis) =>
      set((state) => {
        // Add IDs to detections
        const detectionsWithIds = analysis.detections.map(detection => ({
          ...detection,
          id: `det_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
        }));
        
        state.analyses[analysis.id] = {
          ...analysis,
          detections: detectionsWithIds
        };
      }),

    updateDetection: (detectionId, updates) =>
      set((state) => {
        const currentAnalysis = state.currentAnalysis;
        if (currentAnalysis) {
          const detectionIndex = currentAnalysis.detections.findIndex(d => d.id === detectionId);
          if (detectionIndex >= 0) {
            Object.assign(currentAnalysis.detections[detectionIndex], updates);
            state.analyses[currentAnalysis.id] = currentAnalysis;
          }
        }
      }),

    setLoading: (loading) =>
      set((state) => {
        state.isLoading = loading;
      }),

    setError: (error) =>
      set((state) => {
        state.error = error;
      }),

    updateRedactionConfig: (config) =>
      set((state) => {
        Object.assign(state.redactionConfig, config);
      }),

    approveAllDetections: () =>
      set((state) => {
        if (state.currentAnalysis) {
          state.currentAnalysis.detections.forEach(detection => {
            detection.approved = true;
          });
          state.analyses[state.currentAnalysis.id] = state.currentAnalysis;
        }
      }),

    rejectAllDetections: () =>
      set((state) => {
        if (state.currentAnalysis) {
          state.currentAnalysis.detections.forEach(detection => {
            detection.approved = false;
          });
          state.analyses[state.currentAnalysis.id] = state.currentAnalysis;
        }
      }),
    })),
    PERSIST_OPTIONS
  )
);