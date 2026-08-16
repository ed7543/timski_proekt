import { apiFetch, apiFetchRaw } from './client';
import type {
  ConversationOut,
  ConversationDetailOut,
  ConversationCreate,
  ConversationUpdate,
} from '../types/conversation';

export function listConversations(search?: string): Promise<ConversationOut[]> {
  const qs = search ? `?search=${encodeURIComponent(search)}` : '';
  return apiFetch<ConversationOut[]>(`/api/conversations${qs}`);
}

export function getConversation(id: number): Promise<ConversationDetailOut> {
  return apiFetch<ConversationDetailOut>(`/api/conversations/${id}`);
}

export function createConversation(payload: ConversationCreate = {}): Promise<ConversationOut> {
  return apiFetch<ConversationOut>('/api/conversations', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function renameConversation(id: number, payload: ConversationUpdate): Promise<ConversationOut> {
  return apiFetch<ConversationOut>(`/api/conversations/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function deleteConversation(id: number): Promise<void> {
  return apiFetch<void>(`/api/conversations/${id}`, { method: 'DELETE' });
}

export async function exportConversation(id: number, format: 'markdown' | 'json'): Promise<{ blob: Blob; filename: string }> {
  const resp = await apiFetchRaw(`/api/conversations/${id}/export?format=${format}`);
  const blob = await resp.blob();
  const disposition = resp.headers.get('Content-Disposition') || '';
  const match = disposition.match(/filename="([^"]+)"/);
  const filename = match ? match[1] : `conversation-${id}.${format === 'json' ? 'json' : 'md'}`;
  return { blob, filename };
}
