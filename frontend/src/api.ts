/** API client for DocMind backend **/

export interface User {
  id: string;
  email: string;
  full_name: string | null;
  role: string;
  is_active: boolean;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface ProcessingStage {
  stage: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  progress_percent: number;
  error_message?: string | null;
  duration_ms?: number | null;
}

export interface DocumentItem {
  id: string;
  original_name: string;
  size_bytes: number;
  current_version: number;
  status: 'queued' | 'processing' | 'ready' | 'failed';
  error_message?: string | null;
  created_at: string;
  updated_at: string;
}

export interface DocumentStatus {
  id: string;
  status: 'queued' | 'processing' | 'ready' | 'failed';
  error_message?: string | null;
  stages: ProcessingStage[];
}

export interface DocumentDetail extends DocumentItem {
  download_url?: string | null;
}

const TOKEN_KEY = 'docmind_token';

export const getStoredToken = (): string | null => localStorage.getItem(TOKEN_KEY);
export const setStoredToken = (token: string): void => localStorage.setItem(TOKEN_KEY, token);
export const clearStoredToken = (): void => localStorage.removeItem(TOKEN_KEY);

const authHeaders = (): HeadersInit => {
  const token = getStoredToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
};

export async function login(email: string, password: string): Promise<AuthResponse> {
  const resp = await fetch('/api/v1/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: 'Login failed' }));
    throw new Error(err.detail || 'Login failed');
  }
  const data: AuthResponse = await resp.json();
  setStoredToken(data.access_token);
  return data;
}

export async function signup(email: string, password: string, fullName?: string): Promise<AuthResponse> {
  const resp = await fetch('/api/v1/auth/signup', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, full_name: fullName, role: 'user' }),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: 'Registration failed' }));
    throw new Error(err.detail || 'Registration failed');
  }
  const data: AuthResponse = await resp.json();
  setStoredToken(data.access_token);
  return data;
}

export async function getMe(): Promise<User> {
  const resp = await fetch('/api/v1/auth/me', {
    headers: authHeaders(),
  });
  if (!resp.ok) {
    throw new Error('Not authenticated');
  }
  return resp.json();
}

export async function listDocuments(): Promise<DocumentItem[]> {
  const resp = await fetch('/api/v1/documents', {
    headers: authHeaders(),
  });
  if (!resp.ok) {
    throw new Error('Failed to fetch documents');
  }
  return resp.json();
}

export async function getDocumentStatus(id: string): Promise<DocumentStatus> {
  const resp = await fetch(`/api/v1/documents/${id}/status`, {
    headers: authHeaders(),
  });
  if (!resp.ok) {
    throw new Error('Failed to fetch document status');
  }
  return resp.json();
}

export async function getDocumentDetail(id: string): Promise<DocumentDetail> {
  const resp = await fetch(`/api/v1/documents/${id}`, {
    headers: authHeaders(),
  });
  if (!resp.ok) {
    throw new Error('Failed to fetch document details');
  }
  return resp.json();
}

export async function uploadDocument(file: File): Promise<DocumentItem> {
  const formData = new FormData();
  formData.append('file', file);

  const resp = await fetch('/api/v1/documents', {
    method: 'POST',
    headers: authHeaders(),
    body: formData,
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: 'Upload failed' }));
    throw new Error(err.detail || 'Upload failed');
  }
  return resp.json();
}

export async function deleteDocument(id: string): Promise<void> {
  const resp = await fetch(`/api/v1/documents/${id}`, {
    method: 'DELETE',
    headers: authHeaders(),
  });
  if (!resp.ok) {
    throw new Error('Failed to delete document');
  }
}

// --- Chat & Multi-Agent Retrieval API ---

export interface Citation {
  document_id: string;
  filename?: string;
  page_number: number;
  section?: string;
  bbox?: number[];
  preview_text?: string;
}

export interface ChatQueryRequest {
  query: string;
  document_ids?: string[] | null;
  conversation_id?: string | null;
  use_agent?: boolean;
}

export interface ChatQueryResponse {
  conversation_id: string;
  message_id: string;
  answer: string;
  citations: Citation[];
  retrieved_chunks: Citation[];
  model_used: string;
  fallback_occurred: boolean;
  has_sufficient_evidence: boolean;
  verification: {
    is_verified?: boolean;
    citation_coverage?: number;
    details?: string;
  };
}

export interface MessageItem {
  id: string;
  conversation_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  citations: Citation[];
  meta_info: Record<string, any>;
  created_at: string;
}

export interface ConversationSummary {
  id: string;
  title: string;
  document_id?: string | null;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface ConversationDetail {
  id: string;
  title: string;
  document_id?: string | null;
  created_at: string;
  updated_at: string;
  messages: MessageItem[];
}

export async function queryDocuments(req: ChatQueryRequest): Promise<ChatQueryResponse> {
  const resp = await fetch('/api/v1/chat/query', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders(),
    },
    body: JSON.stringify(req),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: 'Query failed' }));
    throw new Error(err.detail || 'Query failed');
  }
  return resp.json();
}

export async function listConversations(): Promise<ConversationSummary[]> {
  const resp = await fetch('/api/v1/chat/conversations', {
    headers: authHeaders(),
  });
  if (!resp.ok) {
    throw new Error('Failed to fetch conversations');
  }
  return resp.json();
}

export async function getConversation(id: string): Promise<ConversationDetail> {
  const resp = await fetch(`/api/v1/chat/conversations/${id}`, {
    headers: authHeaders(),
  });
  if (!resp.ok) {
    throw new Error('Failed to fetch conversation');
  }
  return resp.json();
}

export async function deleteConversation(id: string): Promise<void> {
  const resp = await fetch(`/api/v1/chat/conversations/${id}`, {
    method: 'DELETE',
    headers: authHeaders(),
  });
  if (!resp.ok) {
    throw new Error('Failed to delete conversation');
  }
}
