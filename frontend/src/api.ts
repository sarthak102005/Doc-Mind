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
