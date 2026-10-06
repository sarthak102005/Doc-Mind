import React, { useEffect, useState, useCallback } from 'react';
import { User, DocumentItem, getMe, listDocuments, clearStoredToken, getStoredToken } from './api';
import { Navbar } from './components/Navbar';
import { AuthModal } from './components/AuthModal';
import { UploadDropzone } from './components/UploadDropzone';
import { DocumentList } from './components/DocumentList';
import { LayersIcon, RefreshIcon } from './components/icons';

export const App: React.FC = () => {
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);

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

  return (
    <div>
      <Navbar user={currentUser} onLogout={handleLogout} />

      <main className="container">
        {!currentUser ? (
          <AuthModal onSuccess={(user) => setCurrentUser(user)} />
        ) : (
          <div>
            {/* Header info */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '2rem' }}>
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
                    <span>Phase 1 Data Layer</span>
                  </span>
                </div>
                <h1 style={{ fontSize: '1.875rem', fontWeight: 800, letterSpacing: '-0.025em' }}>
                  Document Intelligence Hub
                </h1>
                <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginTop: '0.25rem' }}>
                  Manage enterprise documents, monitor ingestion stages, and verify access control.
                </p>
              </div>

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
        )}
      </main>
    </div>
  );
};
export default App;
