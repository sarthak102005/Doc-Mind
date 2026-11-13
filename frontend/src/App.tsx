import React, { useEffect, useState, useCallback } from 'react';
import { User, DocumentItem, getMe, listDocuments, clearStoredToken, getStoredToken } from './api';
import { Navbar } from './components/Navbar';
import { AuthModal } from './components/AuthModal';
import { UploadDropzone } from './components/UploadDropzone';
import { DocumentList } from './components/DocumentList';
import { ChatPane } from './components/ChatPane';
import { LayersIcon, RefreshIcon } from './components/icons';

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
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '1rem' }}>
          <div className="spinner" style={{ width: '32px', height: '32px' }} />
          <span style={{ color: 'var(--text-dim)', fontSize: '0.875rem' }}>Loading DocMind...</span>
        </div>
      </div>
    );
  }

  const readyCount = documents.filter((d) => d.status === 'ready').length;

  return (
    <div>
      <Navbar user={currentUser} onLogout={handleLogout} />

      <main className="container">
        {!currentUser ? (
          <AuthModal onSuccess={(user) => setCurrentUser(user)} />
        ) : (
          <div>
            {/* Header info */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '1.5rem' }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                  <span
                    style={{
                      background: 'rgba(99, 102, 241, 0.15)',
                      color: '#818cf8',
                      fontSize: '0.75rem',
                      fontWeight: 600,
                      padding: '0.2rem 0.6rem',
                      borderRadius: '6px',
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '0.35rem',
                    }}
                  >
                    <LayersIcon size={13} />
                    <span>Multimodal Intelligence Layer</span>
                  </span>
                </div>
                <h1 style={{ fontSize: '1.875rem', fontWeight: 800, letterSpacing: '-0.025em' }}>
                  Document Intelligence Hub
                </h1>
                <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginTop: '0.25rem' }}>
                  End-to-end multimodal document ingestion, dense Qdrant vector indexing, and grounded citation Q&A.
                </p>
              </div>

              <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
                <button
                  className="btn btn-secondary"
                  disabled={refreshing}
                  onClick={() => fetchDocs()}
                  style={{ padding: '0.5rem 0.9rem', fontSize: '0.8rem' }}
                >
                  <RefreshIcon size={14} className={refreshing ? 'spinner' : ''} />
                  <span>Refresh</span>
                </button>
              </div>
            </div>

            {/* Navigation Tabs */}
            <div
              style={{
                display: 'flex',
                gap: '0.5rem',
                borderBottom: '1px solid var(--border-subtle)',
                marginBottom: '1.5rem',
              }}
            >
              <button
                onClick={() => setActiveTab('documents')}
                style={{
                  background: 'none',
                  border: 'none',
                  borderBottom: activeTab === 'documents' ? '2px solid var(--accent-primary)' : '2px solid transparent',
                  color: activeTab === 'documents' ? 'var(--text-main)' : 'var(--text-muted)',
                  padding: '0.6rem 1rem',
                  fontSize: '0.9rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                  transition: 'all 0.2s',
                }}
              >
                Documents & Ingestion ({documents.length})
              </button>

              <button
                onClick={() => setActiveTab('chat')}
                style={{
                  background: 'none',
                  border: 'none',
                  borderBottom: activeTab === 'chat' ? '2px solid var(--accent-primary)' : '2px solid transparent',
                  color: activeTab === 'chat' ? 'var(--text-main)' : 'var(--text-muted)',
                  padding: '0.6rem 1rem',
                  fontSize: '0.9rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  transition: 'all 0.2s',
                }}
              >
                <span>Document Q&A Chat</span>
                {readyCount > 0 && (
                  <span
                    style={{
                      background: 'rgba(16, 185, 129, 0.2)',
                      color: '#34d399',
                      fontSize: '0.7rem',
                      padding: '0.1rem 0.45rem',
                      borderRadius: '10px',
                    }}
                  >
                    {readyCount} indexed
                  </span>
                )}
              </button>
            </div>

            {/* Tab Views */}
            {activeTab === 'documents' ? (
              <div>
                {/* Upload area */}
                <UploadDropzone onUploadSuccess={handleUploadSuccess} />

                {/* Document table */}
                <div style={{ marginBottom: '1rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <h2 style={{ fontSize: '1.15rem', fontWeight: 600 }}>Your Documents ({documents.length})</h2>
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
