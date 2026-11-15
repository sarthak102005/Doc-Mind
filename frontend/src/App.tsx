import React, { useEffect, useState, useCallback } from 'react';
import { User, DocumentItem, getMe, listDocuments, clearStoredToken, getStoredToken } from './api';
import { Navbar } from './components/Navbar';
import { AuthModal } from './components/AuthModal';
import { UploadDropzone } from './components/UploadDropzone';
import { DocumentList } from './components/DocumentList';
import { ChatPane } from './components/ChatPane';
import { DocPilotLogo, LayersIcon, RefreshIcon, SparklesIcon } from './components/icons';

export const App: React.FC = () => {
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<'documents' | 'chat'>('documents');

  // Fetch initial profile
  useEffect(() => {
    const initAuth = async () => {
      const token = getStoredToken();
      if (!token) {
        setLoading(false);
        return;
      }

      try {
        const user = await getMe();
        setCurrentUser(user);
      } catch {
        clearStoredToken();
        setCurrentUser(null);
      } finally {
        setLoading(false);
      }
    };

    initAuth();
  }, []);

  // Fetch documents
  const fetchDocs = useCallback(async (quiet = false) => {
    if (!quiet) setRefreshing(true);
    try {
      const docs = await listDocuments();
      setDocuments(docs);
    } catch {
      // quiet fail on polling
    } finally {
      if (!quiet) setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    if (currentUser) {
      fetchDocs();
    }
  }, [currentUser, fetchDocs]);

  const handleLogout = () => {
    clearStoredToken();
    setCurrentUser(null);
    setDocuments([]);
  };

  const handleUploadSuccess = (newDoc: DocumentItem) => {
    setDocuments((prev) => [newDoc, ...prev]);
    // Refresh to observe worker status progression
    setTimeout(() => fetchDocs(true), 1000);
  };

  const handleDeleteSuccess = (id: string) => {
    setDocuments((prev) => prev.filter((d) => d.id !== id));
  };

  if (loading) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg-app)' }}>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '1.25rem' }}>
          <DocPilotLogo size={48} />
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <span className="spinner" style={{ width: '16px', height: '16px' }} />
            <span style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', fontWeight: 500 }}>
              Loading DocPilot...
            </span>
          </div>
        </div>
      </div>
    );
  }

  const readyCount = documents.filter((d) => d.status === 'ready').length;
  const processingCount = documents.filter((d) => d.status === 'processing' || d.status === 'queued').length;

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Navbar user={currentUser} onLogout={handleLogout} />

      <main className="container" style={{ flex: 1 }}>
        {!currentUser ? (
          <AuthModal onSuccess={(user) => setCurrentUser(user)} />
        ) : (
          <div>
            {/* Workspace Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1.25rem', marginBottom: '2rem' }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.45rem' }}>
                  <span
                    style={{
                      background: 'var(--brand-muted-blue-subtle)',
                      color: 'var(--brand-navy)',
                      fontSize: '0.72rem',
                      fontWeight: 700,
                      textTransform: 'uppercase',
                      letterSpacing: '0.06em',
                      padding: '0.2rem 0.6rem',
                      borderRadius: '4px',
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '0.35rem',
                      border: '1px solid #D6E3F0',
                    }}
                  >
                    <LayersIcon size={12} />
                    <span>Multimodal Intelligence Layer</span>
                  </span>
                </div>
                <h1 style={{ fontFamily: 'var(--font-display)', fontSize: '1.95rem', fontWeight: 800, color: 'var(--brand-navy)', letterSpacing: '-0.025em' }}>
                  Document Intelligence Hub
                </h1>
                <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginTop: '0.25rem', maxWidth: '640px' }}>
                  Enterprise document ingestion, high-resolution figure extraction, dense vector indexing, and grounded citation Q&A.
                </p>
              </div>

              <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
                <button
                  className="btn btn-secondary"
                  disabled={refreshing}
                  onClick={() => fetchDocs()}
                  style={{ padding: '0.5rem 1rem', fontSize: '0.825rem' }}
                >
                  <RefreshIcon size={14} className={refreshing ? 'spinner' : ''} />
                  <span>Refresh Workspace</span>
                </button>
              </div>
            </div>

            {/* Metric Summary Cards */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                gap: '1rem',
                marginBottom: '2rem',
              }}
            >
              <div className="panel-card" style={{ padding: '1rem 1.25rem' }}>
                <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  Total Documents
                </div>
                <div style={{ fontSize: '1.65rem', fontWeight: 700, color: 'var(--brand-navy)', marginTop: '0.25rem' }}>
                  {documents.length}
                </div>
              </div>

              <div className="panel-card" style={{ padding: '1rem 1.25rem' }}>
                <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  Ready for Querying
                </div>
                <div style={{ fontSize: '1.65rem', fontWeight: 700, color: 'var(--status-success)', marginTop: '0.25rem' }}>
                  {readyCount}
                </div>
              </div>

              <div className="panel-card" style={{ padding: '1rem 1.25rem' }}>
                <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  In Ingestion Pipeline
                </div>
                <div style={{ fontSize: '1.65rem', fontWeight: 700, color: processingCount > 0 ? 'var(--status-warning)' : 'var(--text-secondary)', marginTop: '0.25rem' }}>
                  {processingCount}
                </div>
              </div>

              <div className="panel-card" style={{ padding: '1rem 1.25rem' }}>
                <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  Intelligence Status
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', marginTop: '0.5rem' }}>
                  <span className="pulse-dot" style={{ backgroundColor: 'var(--status-success)' }} />
                  <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--brand-navy)' }}>
                    Vector & Figure Store Active
                  </span>
                </div>
              </div>
            </div>

            {/* Navigation Segmented Tab Bar */}
            <div
              style={{
                display: 'inline-flex',
                background: 'var(--bg-secondary)',
                padding: '0.35rem',
                borderRadius: 'var(--radius-md)',
                border: '1px solid var(--border-subtle)',
                marginBottom: '1.75rem',
                gap: '0.35rem',
              }}
            >
              <button
                onClick={() => setActiveTab('documents')}
                style={{
                  background: activeTab === 'documents' ? '#FFFFFF' : 'transparent',
                  border: 'none',
                  borderRadius: 'var(--radius-sm)',
                  color: activeTab === 'documents' ? 'var(--brand-navy)' : 'var(--text-secondary)',
                  padding: '0.55rem 1.15rem',
                  fontSize: '0.875rem',
                  fontWeight: activeTab === 'documents' ? 700 : 500,
                  cursor: 'pointer',
                  boxShadow: activeTab === 'documents' ? 'var(--shadow-xs)' : 'none',
                  transition: 'all 0.15s ease',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                }}
              >
                <span>Documents & Ingestion</span>
                <span
                  style={{
                    background: activeTab === 'documents' ? 'var(--brand-muted-blue-subtle)' : 'rgba(0,0,0,0.06)',
                    color: activeTab === 'documents' ? 'var(--brand-navy)' : 'var(--text-muted)',
                    fontSize: '0.72rem',
                    padding: '0.1rem 0.45rem',
                    borderRadius: '10px',
                    fontWeight: 600,
                  }}
                >
                  {documents.length}
                </span>
              </button>

              <button
                onClick={() => setActiveTab('chat')}
                style={{
                  background: activeTab === 'chat' ? '#FFFFFF' : 'transparent',
                  border: 'none',
                  borderRadius: 'var(--radius-sm)',
                  color: activeTab === 'chat' ? 'var(--brand-navy)' : 'var(--text-secondary)',
                  padding: '0.55rem 1.15rem',
                  fontSize: '0.875rem',
                  fontWeight: activeTab === 'chat' ? 700 : 500,
                  cursor: 'pointer',
                  boxShadow: activeTab === 'chat' ? 'var(--shadow-xs)' : 'none',
                  transition: 'all 0.15s ease',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                }}
              >
                <SparklesIcon size={15} />
                <span>Multimodal Q&A Workspace</span>
                {readyCount > 0 && (
                  <span
                    style={{
                      background: 'var(--status-success-bg)',
                      color: 'var(--status-success)',
                      fontSize: '0.72rem',
                      padding: '0.1rem 0.45rem',
                      borderRadius: '10px',
                      fontWeight: 600,
                      border: '1px solid var(--status-success-border)',
                    }}
                  >
                    {readyCount} ready
                  </span>
                )}
              </button>
            </div>

            {/* Tab Views */}
            {activeTab === 'documents' ? (
              <div>
                <UploadDropzone onUploadSuccess={handleUploadSuccess} />

                <div style={{ marginBottom: '1rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <h2 style={{ fontSize: '1.15rem', fontWeight: 700, color: 'var(--brand-navy)', letterSpacing: '-0.02em' }}>
                    Indexed Document Repository ({documents.length})
                  </h2>
                </div>

                <DocumentList
                  documents={documents}
                  onRefresh={() => fetchDocs(true)}
                  onDeleteSuccess={handleDeleteSuccess}
                />
              </div>
            ) : (
              <ChatPane documents={documents} />
            )}
          </div>
        )}
      </main>
    </div>
  );
};

export default App;
