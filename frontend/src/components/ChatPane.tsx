import React, { useState, useEffect, useRef } from 'react';
import {
  DocumentItem,
  ConversationSummary,
  MessageItem,
  Citation,
  queryDocuments,
  listConversations,
  getConversation,
  deleteConversation,
} from '../api';
import { RefreshIcon } from './icons';

interface ChatPaneProps {
  documents: DocumentItem[];
}

export const ChatPane: React.FC<ChatPaneProps> = ({ documents }) => {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [messages, setMessages] = useState<MessageItem[]>([]);
  const [inputQuery, setInputQuery] = useState('');
  const [selectedDocId, setSelectedDocId] = useState<string>('all');
  const [useAgent, setUseAgent] = useState(false);
  const [loading, setLoading] = useState(false);
  const [expandedSources, setExpandedSources] = useState<Record<string, boolean>>({});
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
  const handleSend = async () => {
    const q = inputQuery.trim();
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
        meta_info: {
          model_used: res.model_used,
          fallback_occurred: res.fallback_occurred,
          has_sufficient_evidence: res.has_sufficient_evidence,
          verification: res.verification,
          retrieved_chunks: res.retrieved_chunks,
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
              background: 'rgba(99, 102, 241, 0.2)',
              color: '#a5b4fc',
              border: '1px solid rgba(99, 102, 241, 0.4)',
              borderRadius: '4px',
              padding: '0 4px',
              margin: '0 2px',
              fontSize: '0.85em',
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
      className="glass-panel"
      style={{
        display: 'flex',
        height: '680px',
        overflow: 'hidden',
        marginTop: '1.5rem',
      }}
    >
      {/* Sidebar: Conversation history */}
      <div
        style={{
          width: '260px',
          borderRight: '1px solid var(--border-subtle)',
          display: 'flex',
          flexDirection: 'column',
          background: 'rgba(15, 20, 34, 0.5)',
        }}
      >
        <div style={{ padding: '1rem', borderBottom: '1px solid var(--border-subtle)' }}>
          <button
            className="btn btn-primary"
            onClick={handleNewChat}
            style={{ width: '100%', fontSize: '0.85rem', padding: '0.5rem' }}
          >
            + New Chat
          </button>
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: '0.5rem' }}>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', padding: '0.5rem', fontWeight: 600 }}>
            RECENT CONVERSATIONS
          </div>
          {conversations.length === 0 ? (
            <div style={{ padding: '0.5rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              No conversations yet.
            </div>
          ) : (
            conversations.map((c) => (
              <div
                key={c.id}
                onClick={() => selectConversation(c.id)}
                style={{
                  padding: '0.6rem 0.75rem',
                  borderRadius: 'var(--radius-sm)',
                  marginBottom: '0.35rem',
                  cursor: 'pointer',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  background: activeConvId === c.id ? 'rgba(99, 102, 241, 0.2)' : 'transparent',
                  border: activeConvId === c.id ? '1px solid rgba(99, 102, 241, 0.4)' : '1px solid transparent',
                  transition: 'background 0.2s',
                }}
              >
                <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>
                  <div style={{ fontSize: '0.85rem', fontWeight: 500, color: 'var(--text-main)' }}>
                    {c.title || 'Conversation'}
                  </div>
                  <div style={{ fontSize: '0.7rem', color: 'var(--text-dim)' }}>
                    {c.message_count} messages
                  </div>
                </div>
                <button
                  onClick={(e) => handleDeleteConv(e, c.id)}
                  title="Delete chat"
                  style={{
                    background: 'none',
                    border: 'none',
                    color: 'var(--text-dim)',
                    cursor: 'pointer',
                    fontSize: '1rem',
                    padding: '0 4px',
                  }}
                >
                  &times;
                </button>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Main Chat Area */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
        {/* Controls Bar */}
        <div
          style={{
            padding: '0.75rem 1.25rem',
            borderBottom: '1px solid var(--border-subtle)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            background: 'rgba(15, 20, 34, 0.3)',
          }}
        >
          {/* Document Scope Selector */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Scope:</span>
            <select
              value={selectedDocId}
              onChange={(e) => setSelectedDocId(e.target.value)}
              style={{
                background: 'var(--bg-secondary)',
                color: 'var(--text-main)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-sm)',
                padding: '0.35rem 0.6rem',
                fontSize: '0.8rem',
                outline: 'none',
              }}
            >
              <option value="all">All Documents ({readyDocs.length} Indexed)</option>
              {readyDocs.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.original_name}
                </option>
              ))}
            </select>
          </div>

          {/* Workflow Toggle */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', cursor: 'pointer', fontSize: '0.8rem' }}>
              <input
                type="checkbox"
                checked={useAgent}
                onChange={(e) => setUseAgent(e.target.checked)}
                style={{ accentColor: 'var(--accent-primary)' }}
              />
              <span style={{ color: useAgent ? 'var(--accent-cyan)' : 'var(--text-muted)' }}>
                {useAgent ? 'LangGraph Agent (Multi-Step)' : 'Standard Grounded RAG'}
              </span>
            </label>
          </div>
        </div>

        {/* Message Thread */}
        <div
          style={{
            flex: 1,
            overflowY: 'auto',
            padding: '1.25rem',
            display: 'flex',
            flexDirection: 'column',
            gap: '1rem',
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
                color: 'var(--text-muted)',
                textAlign: 'center',
              }}
            >
              <div style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>🔍</div>
              <div style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-main)' }}>
                DocMind Grounded Multimodal Intelligence
              </div>
              <p style={{ maxWidth: '420px', fontSize: '0.85rem', marginTop: '0.5rem', lineHeight: 1.6 }}>
                Ask complex questions, extract specific metrics from tables, or locate diagrams across your indexed documents. Answers are strictly grounded with verifiable page citations.
              </p>
              {readyDocs.length === 0 && (
                <div style={{ marginTop: '1rem', color: 'var(--accent-amber)', fontSize: '0.8rem' }}>
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
                  maxWidth: '82%',
                }}
              >
                {/* Bubble */}
                <div
                  style={{
                    padding: '0.85rem 1.15rem',
                    borderRadius: 'var(--radius-md)',
                    background:
                      m.role === 'user'
                        ? 'linear-gradient(135deg, var(--accent-primary), #4f46e5)'
                        : 'rgba(26, 34, 54, 0.95)',
                    color: '#ffffff',
                    border: m.role === 'user' ? 'none' : '1px solid var(--border-subtle)',
                    fontSize: '0.9rem',
                    lineHeight: 1.5,
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word',
                  }}
                >
                  {m.role === 'assistant' ? renderFormattedAnswer(m.content) : m.content}
                </div>

                {/* Assistant metadata footer */}
                {m.role === 'assistant' && (
                  <div
                    style={{
                      display: 'flex',
                      flexWrap: 'wrap',
                      alignItems: 'center',
                      gap: '0.5rem',
                      marginTop: '0.4rem',
                      fontSize: '0.72rem',
                    }}
                  >
                    {m.meta_info?.model_used && (
                      <span
                        style={{
                          background: 'rgba(255, 255, 255, 0.06)',
                          color: 'var(--text-muted)',
                          padding: '0.15rem 0.45rem',
                          borderRadius: '4px',
                        }}
                      >
                        Model: {m.meta_info.model_used.split('/').pop()}
                      </span>
                    )}

                    {m.meta_info?.verification?.is_verified && (
                      <span
                        style={{
                          background: 'rgba(16, 185, 129, 0.15)',
                          color: '#34d399',
                          padding: '0.15rem 0.45rem',
                          borderRadius: '4px',
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
                          color: 'var(--accent-cyan)',
                          cursor: 'pointer',
                          textDecoration: 'underline',
                          fontSize: '0.72rem',
                          padding: 0,
                        }}
                      >
                        {expandedSources[m.id]
                          ? 'Hide Evidence Sources'
                          : `View ${m.citations.length} Cited Sources`}
                      </button>
                    )}
                  </div>
                )}

                {/* Expandable Evidence Drawer */}
                {expandedSources[m.id] && m.citations && m.citations.length > 0 && (
                  <div
                    style={{
                      marginTop: '0.5rem',
                      background: 'rgba(15, 20, 34, 0.9)',
                      border: '1px solid rgba(99, 102, 241, 0.3)',
                      borderRadius: 'var(--radius-sm)',
                      padding: '0.75rem',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '0.5rem',
                    }}
                  >
                    <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-main)' }}>
                      Retrieved Grounding Evidence:
                    </div>
                    {m.citations.map((c, idx) => (
                      <div
                        key={idx}
                        style={{
                          padding: '0.5rem',
                          background: 'rgba(255, 255, 255, 0.03)',
                          borderRadius: '4px',
                          borderLeft: '2px solid var(--accent-primary)',
                        }}
                      >
                        <div
                          style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            fontSize: '0.75rem',
                            fontWeight: 600,
                            color: '#818cf8',
                            marginBottom: '0.2rem',
                          }}
                        >
                          <span>Doc: {c.filename || c.document_id}</span>
                          <span>Page {c.page_number}</span>
                        </div>
                        {c.section && (
                          <div style={{ fontSize: '0.7rem', color: 'var(--text-dim)', marginBottom: '0.25rem' }}>
                            Section: {c.section}
                          </div>
                        )}
                        {c.preview_text && (
                          <div
                            style={{
                              fontSize: '0.75rem',
                              color: 'var(--text-muted)',
                              lineHeight: 1.4,
                              fontFamily: 'var(--font-mono)',
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
            ))
          )}

          {loading && (
            <div
              style={{
                alignSelf: 'flex-start',
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                padding: '0.75rem 1rem',
                borderRadius: 'var(--radius-md)',
                background: 'rgba(26, 34, 54, 0.7)',
                color: 'var(--text-muted)',
                fontSize: '0.85rem',
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

        {/* Input Bar */}
        <div
          style={{
            padding: '0.85rem 1.25rem',
            borderTop: '1px solid var(--border-subtle)',
            background: 'rgba(10, 13, 20, 0.6)',
            display: 'flex',
            gap: '0.75rem',
            alignItems: 'center',
          }}
        >
          <input
            type="text"
            placeholder={
              readyDocs.length === 0
                ? 'Upload and wait for a document to be indexed...'
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
              background: 'var(--bg-secondary)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-sm)',
              padding: '0.65rem 0.9rem',
              color: 'var(--text-main)',
              fontSize: '0.88rem',
              outline: 'none',
            }}
          />
          <button
            className="btn btn-primary"
            onClick={handleSend}
            disabled={loading || !inputQuery.trim()}
            style={{ padding: '0.65rem 1.2rem', fontSize: '0.85rem' }}
          >
            {loading ? 'Thinking...' : 'Send'}
          </button>
        </div>
      </div>
    </div>
  );
};
