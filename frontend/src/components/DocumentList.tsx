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
            <span className="spinner" style={{ width: '10px', height: '10px' }} />
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
      <div
        className="panel-card"
        style={{
          padding: '4rem 2rem',
          textAlign: 'center',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <div
          style={{
            width: '60px',
            height: '60px',
            borderRadius: '50%',
            background: 'var(--bg-secondary)',
            color: 'var(--brand-muted-blue)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            marginBottom: '1rem',
          }}
        >
          <FileTextIcon size={28} />
        </div>
        <h3 style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.35rem' }}>
          No documents uploaded yet
        </h3>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem', maxWidth: '380px', lineHeight: 1.5 }}>
          Upload technical manuals, specification sheets, or reports to begin multimodal extraction and grounded Q&A.
        </p>
      </div>
    );
  }

  return (
    <div className="panel-card" style={{ overflow: 'hidden' }}>
      <div style={{ overflowX: 'auto' }}>
        <table className="data-table">
          <thead>
            <tr>
              <th style={{ minWidth: '280px' }}>Document</th>
              <th style={{ minWidth: '90px' }}>Size</th>
              <th style={{ minWidth: '120px' }}>Status</th>
              <th style={{ minWidth: '140px' }}>Uploaded</th>
              <th style={{ minWidth: '110px', textAlign: 'right' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {documents.map((doc) => (
              <tr key={doc.id}>
                <td>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem' }}>
                    <div
                      style={{
                        width: '36px',
                        height: '36px',
                        borderRadius: 'var(--radius-sm)',
                        background: 'var(--brand-muted-blue-subtle)',
                        color: 'var(--brand-navy)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        flexShrink: 0,
                      }}
                    >
                      <FileTextIcon size={18} />
                    </div>
                    <div style={{ minWidth: 0 }}>
                      <div
                        style={{
                          fontWeight: 600,
                          color: 'var(--text-primary)',
                          fontSize: '0.88rem',
                          whiteSpace: 'nowrap',
                          textOverflow: 'ellipsis',
                          overflow: 'hidden',
                          maxWidth: '380px',
                        }}
                        title={doc.original_name}
                      >
                        {doc.original_name}
                      </div>
                      <div style={{ fontSize: '0.73rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginTop: '0.1rem' }}>
                        v{doc.current_version} • <span title={doc.id}>{doc.id.slice(0, 8)}...</span>
                      </div>
                    </div>
                  </div>
                </td>
                <td style={{ color: 'var(--text-secondary)', fontSize: '0.825rem' }}>
                  {formatBytes(doc.size_bytes)}
                </td>
                <td>{renderStatusBadge(doc.status)}</td>
                <td style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>
                  {formatDate(doc.created_at)}
                </td>
                <td style={{ textAlign: 'right' }}>
                  <div style={{ display: 'inline-flex', gap: '0.4rem' }}>
                    <button
                      className="btn btn-secondary"
                      onClick={() => handleDownload(doc)}
                      style={{ padding: '0.4rem 0.65rem' }}
                      title="Open / Download PDF"
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
                      {deletingId === doc.id ? (
                        <span className="spinner" style={{ width: '12px', height: '12px' }} />
                      ) : (
                        <TrashIcon size={14} />
                      )}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
