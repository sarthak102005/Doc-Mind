import React, { useState, useEffect, useRef } from 'react';
import {
  DocumentItem,
  ConversationSummary,
  MessageItem,
  Citation,
  ImageAttachment,
  authHeaders,
  queryDocuments,
  listConversations,
  getConversation,
  deleteConversation,
} from '../api';
import { DocPilotLogo, PlusIcon, RefreshIcon, SparklesIcon, TrashIcon } from './icons';

interface ChatPaneProps {
  documents: DocumentItem[];
}

const FigureImageCard: React.FC<{
  image: ImageAttachment;
  onOpenModal: (url: string, title: string) => void;
}> = ({ image, onOpenModal }) => {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<boolean>(false);

  useEffect(() => {
    let active = true;
    let createdUrl: string | null = null;

    const fetchImage = async () => {
      try {
        setLoading(true);
        setError(false);
        const resp = await fetch(image.image_url, {
          headers: authHeaders(),
        });
        if (!resp.ok) {
          throw new Error(`Failed to load image: ${resp.status}`);
        }
        const blob = await resp.blob();
        if (active) {
          createdUrl = URL.createObjectURL(blob);
          setBlobUrl(createdUrl);
          setLoading(false);
        }
      } catch {
        if (active) {
          setError(true);
          setLoading(false);
        }
      }
    };

    fetchImage();

    return () => {
      active = false;
      if (createdUrl) {
        URL.revokeObjectURL(createdUrl);
      }
    };
  }, [image.image_url]);

  const title = image.caption || `Page ${image.page_number} Technical Figure`;

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        background: '#FFFFFF',
        border: '1px solid var(--border-subtle)',
        borderRadius: 'var(--radius-md)',
        overflow: 'hidden',
        maxWidth: '380px',
        marginTop: '0.65rem',
        boxShadow: 'var(--shadow-sm)',
        transition: 'all 0.2s ease',
      }}
    >
      {/* Header Bar */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0.45rem 0.75rem',
          background: 'var(--bg-card-subtle)',
          borderBottom: '1px solid var(--border-subtle)',
          fontSize: '0.75rem',
          color: 'var(--text-secondary)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', overflow: 'hidden' }}>
          <span style={{ color: 'var(--brand-muted-blue)', fontWeight: 600 }}>📷</span>
          <span style={{ whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden', maxWidth: '210px', fontWeight: 500 }}>
            {image.filename || 'Extracted Document Figure'}
          </span>
        </div>
        <span
          style={{
            background: 'var(--brand-muted-blue-subtle)',
            color: 'var(--brand-navy)',
            border: '1px solid #D3DFEC',
            padding: '0.12rem 0.5rem',
            borderRadius: '4px',
            fontSize: '0.7rem',
            fontWeight: 600,
            whiteSpace: 'nowrap',
          }}
        >
          Page {image.page_number}
        </span>
      </div>

      {/* Image Preview Area */}
      <div
        style={{
          position: 'relative',
          background: '#F8F7F4',
          minHeight: '140px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: blobUrl ? 'zoom-in' : 'default',
          padding: '0.5rem',
        }}
        onClick={() => {
          if (blobUrl) onOpenModal(blobUrl, title);
        }}
      >
        {loading && (
          <div style={{ padding: '2rem', color: 'var(--text-muted)', fontSize: '0.8rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span className="spinner" style={{ width: '12px', height: '12px' }} />
            <span>Loading PDF image crop...</span>
          </div>
        )}
        {error && (
          <div style={{ padding: '2rem', color: 'var(--status-error)', fontSize: '0.8rem' }}>
            Figure preview unavailable
          </div>
        )}
        {blobUrl && !loading && (
          <img
            src={blobUrl}
            alt={title}
            style={{
              maxWidth: '100%',
              maxHeight: '260px',
              objectFit: 'contain',
              display: 'block',
              borderRadius: 'var(--radius-xs)',
            }}
          />
        )}
      </div>

      {/* Caption footer */}
      {image.caption && (
        <div
          style={{
            padding: '0.5rem 0.75rem',
            fontSize: '0.75rem',
            color: 'var(--text-secondary)',
            lineHeight: 1.45,
            borderTop: '1px solid var(--border-subtle)',
            background: '#FFFFFF',
          }}
        >
          {image.caption}
        </div>
      )}
    </div>
  );
};

export const ChatPane: React.FC<ChatPaneProps> = ({ documents }) => {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [messages, setMessages] = useState<MessageItem[]>([]);
  const [inputQuery, setInputQuery] = useState('');
  const [selectedDocId, setSelectedDocId] = useState<string>('all');
  const [useAgent, setUseAgent] = useState(false);
  const [loading, setLoading] = useState(false);
  const [expandedSources, setExpandedSources] = useState<Record<string, boolean>>({});
  const [modalImage, setModalImage] = useState<{ url: string; title: string } | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Ready documents for filtering
  const readyDocs = documents.filter((d) => d.status === 'ready');

  // Load conversations
  const loadConversations = async () => {
    try {
      const list = await listConversations();
      setConversations(list);
    } catch {
      // quiet fail
    }
  };

  useEffect(() => {
    loadConversations();
  }, []);

  // Select conversation
  const selectConversation = async (convId: string) => {
    setActiveConvId(convId);
    try {
      const detail = await getConversation(convId);
      setMessages(detail.messages || []);
    } catch {
      setMessages([]);
    }
  };

  // Start new conversation
  const handleNewChat = () => {
    setActiveConvId(null);
    setMessages([]);
    setInputQuery('');
  };

  // Delete conversation
  const handleDeleteConv = async (e: React.MouseEvent, convId: string) => {
    e.stopPropagation();
    try {
      await deleteConversation(convId);
      if (activeConvId === convId) {
        handleNewChat();
      }
      loadConversations();
    } catch (err) {
      console.error('Failed to delete conversation', err);
    }
  };

  // Auto-scroll to bottom of chat
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  // Send query
  const handleSend = async (queryOverride?: string) => {
    const q = (queryOverride || inputQuery).trim();
    if (!q || loading) return;

    // Optimistically show user message
    const tempUserMsg: MessageItem = {
      id: `temp-${Date.now()}`,
      conversation_id: activeConvId || 'new',
      role: 'user',
      content: q,
      citations: [],
      meta_info: {},
      created_at: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, tempUserMsg]);
    setInputQuery('');
    setLoading(true);

    try {
      const docFilter = selectedDocId === 'all' ? null : [selectedDocId];
      const res = await queryDocuments({
        query: q,
        conversation_id: activeConvId,
        document_ids: docFilter,
        use_agent: useAgent,
      });

      if (!activeConvId) {
        setActiveConvId(res.conversation_id);
      }

      const asstMsg: MessageItem = {
        id: res.message_id,
        conversation_id: res.conversation_id,
        role: 'assistant',
        content: res.answer,
        citations: res.citations || [],
        images: res.images || [],
        meta_info: {
          model_used: res.model_used,
          fallback_occurred: res.fallback_occurred,
          has_sufficient_evidence: res.has_sufficient_evidence,
          verification: res.verification,
          retrieved_chunks: res.retrieved_chunks,
          images: res.images || [],
        },
        created_at: new Date().toISOString(),
      };

      setMessages((prev) => [...prev, asstMsg]);
      loadConversations();
    } catch (err: any) {
      const errMsg: MessageItem = {
        id: `err-${Date.now()}`,
        conversation_id: activeConvId || 'new',
        role: 'assistant',
        content: `Error: ${err.message || 'Failed to generate response'}`,
        citations: [],
        meta_info: { is_error: true },
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, errMsg]);
    } finally {
      setLoading(false);
    }
  };

  const toggleSources = (msgId: string) => {
    setExpandedSources((prev) => ({
      ...prev,
      [msgId]: !prev[msgId],
    }));
  };

  // Helper to highlight citation brackets [Doc: ..., Page: ...]
  const renderFormattedAnswer = (content: string) => {
    const parts = content.split(/(\[Doc:[^\]]+\])/gi);
    return parts.map((part, i) => {
      if (part.startsWith('[Doc:') && part.endsWith(']')) {
        return (
          <span
            key={i}
            style={{
              display: 'inline-block',
              background: 'var(--brand-muted-blue-subtle)',
              color: 'var(--brand-navy)',
              border: '1px solid #D3DFEC',
              borderRadius: '4px',
              padding: '0.05rem 0.4rem',
              margin: '0 0.2rem',
              fontSize: '0.82em',
              fontWeight: 600,
            }}
          >
            {part}
          </span>
        );
      }
      return part;
    });
  };

  return (
    <div
      className="panel-card"
      style={{
        display: 'flex',
        height: '740px',
        overflow: 'hidden',
        boxShadow: 'var(--shadow-md)',
      }}
    >
      {/* Sidebar: Conversation history */}
      <div
        style={{
          width: '280px',
          borderRight: '1px solid var(--border-subtle)',
          display: 'flex',
          flexDirection: 'column',
          background: 'var(--bg-secondary)',
          flexShrink: 0,
        }}
      >
        {/* Sidebar Header */}
        <div
          style={{
            padding: '1.1rem 1.15rem',
            borderBottom: '1px solid var(--border-subtle)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <span style={{ fontSize: '0.825rem', fontWeight: 700, color: 'var(--text-primary)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            Conversations
          </span>
          <button
            className="btn btn-secondary"
            onClick={handleNewChat}
            style={{ padding: '0.35rem 0.65rem', fontSize: '0.78rem' }}
            title="Start new conversation"
          >
            <PlusIcon size={14} />
            <span>New</span>
          </button>
        </div>

        {/* Conversation List */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '0.75rem' }}>
          {conversations.length === 0 ? (
            <div style={{ padding: '2rem 1rem', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.825rem' }}>
              No previous threads. Ask a question to begin!
            </div>
          ) : (
            conversations.map((conv) => {
              const isActive = activeConvId === conv.id;
              return (
                <div
                  key={conv.id}
                  onClick={() => selectConversation(conv.id)}
                  style={{
                    padding: '0.7rem 0.85rem',
                    borderRadius: 'var(--radius-sm)',
                    marginBottom: '0.35rem',
                    cursor: 'pointer',
                    background: isActive ? '#FFFFFF' : 'transparent',
                    border: isActive ? '1px solid var(--border-subtle)' : '1px solid transparent',
                    borderLeft: isActive ? '3px solid var(--brand-navy)' : '1px solid transparent',
                    boxShadow: isActive ? 'var(--shadow-xs)' : 'none',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    transition: 'all 0.15s ease',
                  }}
                  onMouseEnter={(e) => {
                    if (!isActive) e.currentTarget.style.backgroundColor = 'var(--bg-hover)';
                  }}
                  onMouseLeave={(e) => {
                    if (!isActive) e.currentTarget.style.backgroundColor = 'transparent';
                  }}
                >
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div
                      style={{
                        fontSize: '0.85rem',
                        fontWeight: isActive ? 600 : 500,
                        color: isActive ? 'var(--brand-navy)' : 'var(--text-primary)',
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                      }}
                    >
                      {conv.title || 'Untitled Thread'}
                    </div>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '0.15rem' }}>
                      {conv.message_count} {conv.message_count === 1 ? 'message' : 'messages'}
                    </div>
                  </div>

                  <button
                    onClick={(e) => handleDeleteConv(e, conv.id)}
                    style={{
                      background: 'none',
                      border: 'none',
                      color: 'var(--text-muted)',
                      cursor: 'pointer',
                      padding: '0.25rem',
                      borderRadius: '4px',
                      display: 'flex',
                      alignItems: 'center',
                    }}
                    title="Delete thread"
                    onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--status-error)')}
                    onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-muted)')}
                  >
                    <TrashIcon size={13} />
                  </button>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* Main Chat Content Area */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: '#FFFFFF', minWidth: 0 }}>
        {/* Chat Control Toolbar */}
        <div
          style={{
            padding: '0.85rem 1.5rem',
            borderBottom: '1px solid var(--border-subtle)',
            display: 'flex',
            flexWrap: 'wrap',
            alignItems: 'center',
            justifyContent: 'space-between',
            background: 'var(--bg-card-subtle)',
            gap: '0.75rem',
          }}
        >
          {/* Document Scope Filter */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
            <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
              Document Scope:
            </span>
            <select
              value={selectedDocId}
              onChange={(e) => setSelectedDocId(e.target.value)}
              style={{
                background: '#FFFFFF',
                border: '1px solid var(--border-strong)',
                borderRadius: 'var(--radius-sm)',
                padding: '0.35rem 0.75rem',
                fontSize: '0.825rem',
                color: 'var(--text-primary)',
                outline: 'none',
                cursor: 'pointer',
                boxShadow: 'var(--shadow-xs)',
              }}
            >
              <option value="all">All Authorized Documents ({readyDocs.length} indexed)</option>
              {readyDocs.map((doc) => (
                <option key={doc.id} value={doc.id}>
                  {doc.original_name}
                </option>
              ))}
            </select>
          </div>

          {/* Reasoning Engine Toggle */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <label
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.5rem',
                cursor: 'pointer',
                fontSize: '0.8rem',
                fontWeight: 600,
                color: useAgent ? 'var(--brand-navy)' : 'var(--text-secondary)',
                background: useAgent ? 'var(--accent-teal-subtle)' : '#FFFFFF',
                border: useAgent ? '1px solid var(--accent-teal)' : '1px solid var(--border-subtle)',
                padding: '0.35rem 0.75rem',
                borderRadius: 'var(--radius-sm)',
                transition: 'all 0.15s ease',
              }}
            >
              <input
                type="checkbox"
                checked={useAgent}
                onChange={(e) => setUseAgent(e.target.checked)}
                style={{ cursor: 'pointer' }}
              />
              <SparklesIcon size={14} className={useAgent ? 'text-teal' : ''} />
              <span>LangGraph Multi-Agent Mode</span>
            </label>
          </div>
        </div>

        {/* Message Thread */}
        <div
          style={{
            flex: 1,
            overflowY: 'auto',
            padding: '1.75rem',
            display: 'flex',
            flexDirection: 'column',
            gap: '1.25rem',
            background: 'var(--bg-app)',
          }}
        >
          {messages.length === 0 ? (
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                height: '100%',
                color: 'var(--text-secondary)',
                textAlign: 'center',
                padding: '2rem',
              }}
            >
              <DocPilotLogo size={44} />
              <div style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--brand-navy)', marginTop: '1rem' }}>
                DocPilot Multimodal Intelligence
              </div>
              <p style={{ maxWidth: '480px', fontSize: '0.875rem', marginTop: '0.5rem', lineHeight: 1.6, color: 'var(--text-secondary)' }}>
                Ask technical questions, cross-examine specification tables, or request high-resolution diagram and photo crops from your documents. Every answer is verifiable and page-cited.
              </p>

              {/* Suggested Questions */}
              <div style={{ marginTop: '1.75rem', display: 'flex', flexWrap: 'wrap', gap: '0.5rem', justifyContent: 'center', maxWidth: '580px' }}>
                {[
                  'i want photo of mag-hd',
                  'Show me the Mini-HD image on page 11.',
                  'What are the specifications of Mag-HD on page 11?',
                ].map((sample, idx) => (
                  <button
                    key={idx}
                    onClick={() => handleSend(sample)}
                    style={{
                      background: '#FFFFFF',
                      border: '1px solid var(--border-subtle)',
                      padding: '0.45rem 0.9rem',
                      borderRadius: 'var(--radius-sm)',
                      fontSize: '0.8rem',
                      color: 'var(--brand-navy)',
                      cursor: 'pointer',
                      boxShadow: 'var(--shadow-xs)',
                      transition: 'all 0.15s ease',
                      fontWeight: 500,
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.borderColor = 'var(--brand-navy)';
                      e.currentTarget.style.transform = 'translateY(-1px)';
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.borderColor = 'var(--border-subtle)';
                      e.currentTarget.style.transform = 'none';
                    }}
                  >
                    ✨ "{sample}"
                  </button>
                ))}
              </div>

              {readyDocs.length === 0 && (
                <div style={{ marginTop: '1.5rem', color: 'var(--status-warning)', fontSize: '0.825rem', background: 'var(--status-warning-bg)', border: '1px solid var(--status-warning-border)', padding: '0.4rem 0.9rem', borderRadius: '4px' }}>
                  Notice: No documents are currently marked ready in Qdrant. Upload a PDF first to begin querying!
                </div>
              )}
            </div>
          ) : (
            messages.map((m) => (
              <div
                key={m.id}
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
                  maxWidth: m.role === 'user' ? '78%' : '88%',
                }}
              >
                {/* User Message Card */}
                {m.role === 'user' ? (
                  <div
                    style={{
                      padding: '0.85rem 1.15rem',
                      borderRadius: 'var(--radius-md) var(--radius-md) var(--radius-xs) var(--radius-md)',
                      background: '#EAE6DC',
                      color: 'var(--text-primary)',
                      border: '1px solid var(--border-strong)',
                      fontSize: '0.9rem',
                      lineHeight: 1.5,
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                      boxShadow: 'var(--shadow-xs)',
                    }}
                  >
                    {m.content}
                  </div>
                ) : (
                  /* Assistant Editorial Response Card */
                  <div
                    style={{
                      padding: '1.25rem 1.4rem',
                      borderRadius: 'var(--radius-md)',
                      background: '#FFFFFF',
                      color: 'var(--text-primary)',
                      border: '1px solid var(--border-subtle)',
                      boxShadow: 'var(--shadow-sm)',
                      fontSize: '0.92rem',
                      lineHeight: 1.6,
                      wordBreak: 'break-word',
                    }}
                  >
                    {/* Answer text */}
                    <div style={{ whiteSpace: 'pre-wrap', color: 'var(--text-primary)' }}>
                      {renderFormattedAnswer(m.content)}
                    </div>

                    {/* Inline Figure Images */}
                    {((m.images && m.images.length > 0) || (m.meta_info?.images && m.meta_info.images.length > 0)) && (
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.85rem', marginTop: '1rem', paddingTop: '0.85rem', borderTop: '1px solid var(--border-subtle)' }}>
                        {((m.images && m.images.length > 0 ? m.images : m.meta_info?.images) || []).map((img: ImageAttachment, idx: number) => (
                          <FigureImageCard
                            key={idx}
                            image={img}
                            onOpenModal={(url, title) => setModalImage({ url, title })}
                          />
                        ))}
                      </div>
                    )}

                    {/* Assistant metadata & citation footer */}
                    <div
                      style={{
                        display: 'flex',
                        flexWrap: 'wrap',
                        alignItems: 'center',
                        gap: '0.65rem',
                        marginTop: '1rem',
                        paddingTop: '0.75rem',
                        borderTop: '1px solid var(--border-subtle)',
                        fontSize: '0.75rem',
                      }}
                    >
                      {m.meta_info?.model_used && (
                        <span
                          style={{
                            background: 'var(--bg-card-subtle)',
                            color: 'var(--text-secondary)',
                            border: '1px solid var(--border-subtle)',
                            padding: '0.15rem 0.5rem',
                            borderRadius: '4px',
                            fontWeight: 500,
                          }}
                        >
                          Model: {m.meta_info.model_used.split('/').pop()}
                        </span>
                      )}

                      {m.meta_info?.verification?.is_verified && (
                        <span
                          style={{
                            background: 'var(--status-success-bg)',
                            color: 'var(--status-success)',
                            border: '1px solid var(--status-success-border)',
                            padding: '0.15rem 0.5rem',
                            borderRadius: '4px',
                            fontWeight: 600,
                          }}
                        >
                          ✓ Verified Grounding
                        </span>
                      )}

                      {m.citations && m.citations.length > 0 && (
                        <button
                          onClick={() => toggleSources(m.id)}
                          style={{
                            background: 'none',
                            border: 'none',
                            color: 'var(--brand-muted-blue)',
                            cursor: 'pointer',
                            textDecoration: 'underline',
                            fontSize: '0.75rem',
                            fontWeight: 600,
                            padding: 0,
                          }}
                        >
                          {expandedSources[m.id]
                            ? 'Hide Evidence Sources'
                            : `View ${m.citations.length} Cited Sources`}
                        </button>
                      )}
                    </div>

                    {/* Expandable Evidence Drawer */}
                    {expandedSources[m.id] && m.citations && m.citations.length > 0 && (
                      <div
                        style={{
                          marginTop: '0.75rem',
                          background: 'var(--bg-card-subtle)',
                          border: '1px solid var(--border-subtle)',
                          borderRadius: 'var(--radius-sm)',
                          padding: '0.85rem',
                          display: 'flex',
                          flexDirection: 'column',
                          gap: '0.65rem',
                        }}
                      >
                        <div style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--brand-navy)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                          Retrieved Grounding Evidence:
                        </div>
                        {m.citations.map((c, idx) => (
                          <div
                            key={idx}
                            style={{
                              padding: '0.65rem',
                              background: '#FFFFFF',
                              borderRadius: '4px',
                              border: '1px solid var(--border-subtle)',
                              borderLeft: '3px solid var(--brand-navy)',
                            }}
                          >
                            <div
                              style={{
                                display: 'flex',
                                justifyContent: 'space-between',
                                fontSize: '0.75rem',
                                fontWeight: 600,
                                color: 'var(--brand-navy)',
                                marginBottom: '0.2rem',
                              }}
                            >
                              <span>Doc: {c.filename || c.document_id}</span>
                              <span style={{ color: 'var(--brand-muted-blue)' }}>Page {c.page_number}</span>
                            </div>
                            {c.section && (
                              <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>
                                Section: {c.section}
                              </div>
                            )}
                            {c.preview_text && (
                              <div
                                style={{
                                  fontSize: '0.75rem',
                                  color: 'var(--text-secondary)',
                                  lineHeight: 1.45,
                                  fontFamily: 'var(--font-mono)',
                                  background: 'var(--bg-app)',
                                  padding: '0.4rem 0.5rem',
                                  borderRadius: '4px',
                                }}
                              >
                                "{c.preview_text.length > 200 ? c.preview_text.slice(0, 200) + '...' : c.preview_text}"
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))
          )}

          {loading && (
            <div
              style={{
                alignSelf: 'flex-start',
                display: 'flex',
                alignItems: 'center',
                gap: '0.6rem',
                padding: '0.75rem 1.15rem',
                borderRadius: 'var(--radius-sm)',
                background: '#FFFFFF',
                color: 'var(--text-secondary)',
                border: '1px solid var(--border-subtle)',
                fontSize: '0.85rem',
                boxShadow: 'var(--shadow-xs)',
              }}
            >
              <RefreshIcon size={14} className="spinner" />
              <span>
                {useAgent
                  ? 'LangGraph executing multi-node retrieval & grounded reasoning...'
                  : 'Retrieving evidence chunks & synthesizing answer...'}
              </span>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input Composer Bar */}
        <div
          style={{
            padding: '1rem 1.5rem',
            borderTop: '1px solid var(--border-subtle)',
            background: '#FFFFFF',
            display: 'flex',
            gap: '0.75rem',
            alignItems: 'center',
          }}
        >
          <input
            type="text"
            placeholder={
              readyDocs.length === 0
                ? 'Upload a document to begin querying...'
                : 'Ask anything grounded in your documents (e.g. "What are the key technical parameters on page 11?")'
            }
            value={inputQuery}
            onChange={(e) => setInputQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleSend();
            }}
            disabled={loading}
            style={{
              flex: 1,
              background: 'var(--bg-card-subtle)',
              border: '1px solid var(--border-strong)',
              borderRadius: 'var(--radius-sm)',
              padding: '0.75rem 1rem',
              color: 'var(--text-primary)',
              fontSize: '0.9rem',
              outline: 'none',
              transition: 'border-color 0.15s ease, box-shadow 0.15s ease',
              boxShadow: 'var(--shadow-xs)',
            }}
            onFocus={(e) => {
              e.currentTarget.style.borderColor = 'var(--brand-navy)';
              e.currentTarget.style.boxShadow = '0 0 0 3px rgba(32, 54, 77, 0.1)';
            }}
            onBlur={(e) => {
              e.currentTarget.style.borderColor = 'var(--border-strong)';
              e.currentTarget.style.boxShadow = 'var(--shadow-xs)';
            }}
          />
          <button
            className="btn btn-primary"
            onClick={() => handleSend()}
            disabled={loading || !inputQuery.trim()}
            style={{ padding: '0.75rem 1.4rem', fontSize: '0.88rem' }}
          >
            {loading ? 'Thinking...' : 'Send'}
          </button>
        </div>
      </div>

      {/* Modal image preview */}
      {modalImage && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(15, 23, 42, 0.75)',
            backdropFilter: 'blur(4px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 9999,
            padding: '2rem',
          }}
          onClick={() => setModalImage(null)}
        >
          <div
            style={{
              position: 'relative',
              maxWidth: '92vw',
              maxHeight: '92vh',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              background: '#FFFFFF',
              borderRadius: 'var(--radius-md)',
              padding: '1.25rem',
              boxShadow: 'var(--shadow-modal)',
              border: '1px solid var(--border-subtle)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ color: 'var(--brand-navy)', marginBottom: '0.85rem', fontWeight: 600, fontSize: '0.92rem', textAlign: 'center' }}>
              {modalImage.title}
            </div>
            <img
              src={modalImage.url}
              alt={modalImage.title}
              style={{
                maxWidth: '100%',
                maxHeight: '75vh',
                borderRadius: 'var(--radius-sm)',
                boxShadow: '0 4px 16px rgba(0,0,0,0.1)',
                border: '1px solid var(--border-subtle)',
              }}
            />
            <button
              onClick={() => setModalImage(null)}
              className="btn btn-secondary"
              style={{
                marginTop: '1rem',
                padding: '0.45rem 1.25rem',
                fontSize: '0.825rem',
              }}
            >
              Close Preview
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
