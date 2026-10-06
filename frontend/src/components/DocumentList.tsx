import React, { useEffect, useState } from 'react';
import { DocumentItem, getDocumentDetail, deleteDocument } from '../api';
import { AlertCircleIcon, CheckCircleIcon, ExternalLinkIcon, FileTextIcon, TrashIcon } from './icons';

interface DocumentListProps {
  documents: DocumentItem[];
  onRefresh: () => void;
  onDeleteSuccess: (id: string) => void;
}

export const DocumentList: React.FC<DocumentListProps> = ({ documents, onRefresh, onDeleteSuccess }) => {
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // Auto-polling for active documents
  useEffect(() => {
    const hasActiveDocs = documents.some((d) => d.status === 'queued' || d.status === 'processing');
    if (!hasActiveDocs) return;

    const interval = setInterval(() => {
      onRefresh();
    }, 2500);

    return () => clearInterval(interval);
  }, [documents, onRefresh]);

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  const formatDate = (isoString: string) => {
    try {
      const d = new Date(isoString);
      return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    } catch {
      return isoString;
    }
  };

  const handleDownload = async (doc: DocumentItem) => {
    try {
      const detail = await getDocumentDetail(doc.id);
      if (detail.download_url) {
        window.open(detail.download_url, '_blank');
      } else {
        alert('Download URL is not available yet.');
      }
    } catch (err: any) {
      alert(`Could not retrieve document: ${err.message}`);
    }
  };

  const handleDelete = async (doc: DocumentItem) => {
    if (!window.confirm(`Are you sure you want to delete "${doc.original_name}"?`)) {
      return;
    }

    setDeletingId(doc.id);
    try {
      await deleteDocument(doc.id);
      onDeleteSuccess(doc.id);
    } catch (err: any) {
      alert(`Failed to delete document: ${err.message}`);
    } finally {
      setDeletingId(null);
    }
  };

  const renderStatusBadge = (status: DocumentItem['status']) => {
    switch (status) {
      case 'queued':
        return (
          <span className="badge badge-queued">
            <span className="pulse-dot" />
            <span>Queued</span>
          </span>
        );
      case 'processing':
        return (
          <span className="badge badge-processing">
            <span className="spinner" />
            <span>Processing</span>
          </span>
        );
      case 'ready':
        return (
          <span className="badge badge-ready">
            <CheckCircleIcon size={12} />
            <span>Ready</span>
          </span>
        );
      case 'failed':
        return (
          <span className="badge badge-failed">
            <AlertCircleIcon size={12} />
            <span>Failed</span>
          </span>
        );
    }
  };

  if (documents.length === 0) {
    return (
      <div className="glass-panel" style={{ padding: '3.5rem', textAlign: 'center' }}>
        <div style={{ color: 'var(--text-dim)', marginBottom: '1rem' }}>
          <FileTextIcon size={48} />
        </div>
        <h3 style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '0.35rem' }}>No documents uploaded yet</h3>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }}>
          Drop sample_1.pdf or any technical manual into the zone above to begin.
        </p>
      </div>
    );
  }

  return (
    <div className="glass-panel" style={{ overflow: 'hidden' }}>
      <table className="data-table">
        <thead>
          <tr>
            <th>Document</th>
            <th>Size</th>
            <th>Status</th>
            <th>Uploaded</th>
            <th style={{ textAlign: 'right' }}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {documents.map((doc) => (
            <tr key={doc.id}>
              <td>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                  <div
                    style={{
                      padding: '0.5rem',
                      borderRadius: '8px',
                      background: 'rgba(99, 102, 241, 0.1)',
                      color: '#818cf8',
                    }}
                  >
                    <FileTextIcon size={18} />
                  </div>
                  <div>
                    <div style={{ fontWeight: 600, color: 'var(--text-main)' }}>{doc.original_name}</div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>
                      v{doc.current_version} • ID: {doc.id.slice(0, 8)}...
                    </div>
                  </div>
                </div>
              </td>
              <td style={{ color: 'var(--text-muted)' }}>{formatBytes(doc.size_bytes)}</td>
              <td>{renderStatusBadge(doc.status)}</td>
              <td style={{ color: 'var(--text-dim)', fontSize: '0.8rem' }}>{formatDate(doc.created_at)}</td>
              <td style={{ textAlign: 'right' }}>
                <div style={{ display: 'inline-flex', gap: '0.5rem' }}>
                  <button
                    className="btn btn-secondary"
                    onClick={() => handleDownload(doc)}
                    style={{ padding: '0.4rem 0.65rem' }}
                    title="Open / Download"
                  >
                    <ExternalLinkIcon size={14} />
                  </button>

                  <button
                    className="btn btn-danger"
                    disabled={deletingId === doc.id}
                    onClick={() => handleDelete(doc)}
                    style={{ padding: '0.4rem 0.65rem' }}
                    title="Delete document"
                  >
                    {deletingId === doc.id ? <span className="spinner" /> : <TrashIcon size={14} />}
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};
