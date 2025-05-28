import React from 'react';
import { Link } from 'react-router-dom';
import { 
  DocumentTextIcon,
  CloudArrowUpIcon,
  EyeIcon,
  CheckCircleIcon,
  TrashIcon
} from '@heroicons/react/24/outline';
import { useDocuments, useHealthCheck, useDeleteDocument } from '../services/api';
import { useStore } from '../store/useStore';

const Dashboard: React.FC = () => {
  const { data: documentsData, isLoading, refetch: refetchDocuments } = useDocuments();
  const { data: healthData } = useHealthCheck();
  const { analyses } = useStore();
  const deleteDocument = useDeleteDocument();

  const handleDeleteDocument = async (documentId: string, event: React.MouseEvent) => {
    event.preventDefault();
    event.stopPropagation();
    
    if (window.confirm('Are you sure you want to delete this document? This action cannot be undone.')) {
      try {
        await deleteDocument.mutateAsync(documentId);
        await refetchDocuments();
      } catch (error) {
        console.error('Error deleting document:', error);
      }
    }
  };

  const totalDocuments = documentsData?.documents?.length || 0;
  const recentDocuments = documentsData?.documents?.slice(0, 5) || [];
  const totalAnalyses = Object.keys(analyses).length;
  const systemStatus = healthData?.status === 'healthy' ? 'Online' : 'Offline';

  const quickActions = [
    {
      title: 'Upload New Document',
      description: 'Upload PDF documents for analysis',
      href: '/upload',
      icon: CloudArrowUpIcon,
      color: 'indigo',
    },
    {
      title: 'Review Redactions',
      description: 'Review and approve detected redactions',
      href: '/review',
      icon: EyeIcon,
      color: 'green',
    },
  ];

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-gray-900">Dashboard</h1>
        <p className="mt-2 text-gray-600">
          Welcome to OpenRecord - Monitor your document redaction activities
        </p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center">
            <DocumentTextIcon className="h-8 w-8 text-indigo-600" />
            <div className="ml-4">
              <p className="text-sm font-medium text-gray-600">Total Documents</p>
              <p className="text-2xl font-bold text-gray-900">{totalDocuments}</p>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center">
            <CheckCircleIcon className="h-8 w-8 text-green-600" />
            <div className="ml-4">
              <p className="text-sm font-medium text-gray-600">Analyses Completed</p>
              <p className="text-2xl font-bold text-gray-900">{totalAnalyses}</p>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center">
            <div className={`h-8 w-8 rounded-full flex items-center justify-center ${
              systemStatus === 'Online' ? 'bg-green-100' : 'bg-red-100'
            }`}>
              <div className={`h-3 w-3 rounded-full ${
                systemStatus === 'Online' ? 'bg-green-500' : 'bg-red-500'
              }`} />
            </div>
            <div className="ml-4">
              <p className="text-sm font-medium text-gray-600">System Status</p>
              <p className="text-2xl font-bold text-gray-900">{systemStatus}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Quick Actions */}
      <div>
        <h2 className="text-xl font-semibold text-gray-900 mb-4">Quick Actions</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {quickActions.map((action) => (
            <Link
              key={action.title}
              to={action.href}
              className="block bg-white rounded-lg shadow hover:shadow-md transition-shadow duration-200 p-6 group"
            >
              <div className="flex items-center">
                <action.icon className={`h-8 w-8 ${
                  action.color === 'indigo' ? 'text-indigo-600' : 'text-green-600'
                }`} />
                <div className="ml-4">
                  <h3 className="text-lg font-medium text-gray-900 group-hover:text-indigo-600">
                    {action.title}
                  </h3>
                  <p className="text-sm text-gray-600">{action.description}</p>
                </div>
              </div>
            </Link>
          ))}
        </div>
      </div>

      {/* Recent Documents */}
      <div className="bg-white rounded-lg shadow">
        <div className="px-6 py-4 border-b border-gray-200">
          <h3 className="text-lg font-medium text-gray-900">Recent Documents</h3>
        </div>
        <div className="p-6">
          {isLoading ? (
            <p className="text-gray-500">Loading documents...</p>
          ) : recentDocuments.length > 0 ? (
            <div className="space-y-4">
              {recentDocuments.map((document) => (
                <div key={document.id} className="group relative flex items-center justify-between hover:bg-gray-50 -mx-2 px-2 py-1.5 rounded">
                  <Link to={`/documents/${document.id}/review`} className="flex-1 flex items-center" onClick={(e) => e.stopPropagation()}>
                    <DocumentTextIcon className="h-6 w-6 text-gray-400 mr-3 flex-shrink-0" />
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-gray-900 truncate">{document.filename}</p>
                      <p className="text-xs text-gray-500">
                        {document.page_count} pages • {new Date(document.uploaded_at).toLocaleDateString()}
                      </p>
                    </div>
                  </Link>
                  <div className="flex items-center space-x-2">
                    <Link
                      to={`/documents/${document.id}/review`}
                      className="text-indigo-600 hover:text-indigo-500 text-sm font-medium whitespace-nowrap px-2 py-1 rounded hover:bg-indigo-50"
                      onClick={(e) => e.stopPropagation()}
                    >
                      Analyze
                    </Link>
                    <button
                      onClick={(e) => handleDeleteDocument(document.id, e)}
                      className="text-gray-400 hover:text-red-600 p-1 rounded-full hover:bg-red-50 transition-colors"
                      title="Delete document"
                      disabled={deleteDocument.isPending}
                    >
                      {deleteDocument.isPending ? (
                        <div className="h-4 w-4 border-2 border-gray-300 border-t-indigo-600 rounded-full animate-spin"></div>
                      ) : (
                        <TrashIcon className="h-4 w-4" />
                      )}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-4">
              <DocumentTextIcon className="mx-auto h-12 w-12 text-gray-400" />
              <h3 className="mt-2 text-sm font-medium text-gray-900">No documents</h3>
              <p className="mt-1 text-sm text-gray-500">Get started by uploading a document.</p>
              <div className="mt-4">
                <Link
                  to="/upload"
                  className="inline-flex items-center px-4 py-2 border border-transparent shadow-sm text-sm font-medium rounded-md text-white bg-indigo-600 hover:bg-indigo-700"
                >
                  Upload Document
                </Link>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Dashboard;