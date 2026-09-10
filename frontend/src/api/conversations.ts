import { apiFetch, apiFetchRaw } from './client';
import type {
  ConversationOut,
  ConversationDetailOut,
  ConversationCreate,
  ConversationUpdate,
  ConversationInviteOut,
  ConversationMemberOut,
  ConversationStatusOut,
} from '../types/conversation';

export function listConversations(search?: string): Promise<ConversationOut[]> {
  const qs = search ? `?search=${encodeURIComponent(search)}` : '';
  return apiFetch<ConversationOut[]>(`/api/conversations${qs}`);
}

export function getConversation(id: number): Promise<ConversationDetailOut> {
  return apiFetch<ConversationDetailOut>(`/api/conversations/${id}`);
}

/** Cheap poll target - a message count + the generating flag, not the full
 * transcript. See useConversationPolling.ts. */
export function getConversationStatus(id: number): Promise<ConversationStatusOut> {
  return apiFetch<ConversationStatusOut>(`/api/conversations/${id}/status`);
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

/** Owner-only. Multi-use until the conversation hits 3 members or the invite expires/is revoked. */
export function createInvite(conversationId: number): Promise<ConversationInviteOut> {
  return apiFetch<ConversationInviteOut>(`/api/conversations/${conversationId}/invites`, { method: 'POST' });
}

export function revokeInvite(conversationId: number, inviteId: number): Promise<void> {
  return apiFetch<void>(`/api/conversations/${conversationId}/invites/${inviteId}`, { method: 'DELETE' });
}

/** Any logged-in user - joins the conversation this invite points to. */
export function acceptInvite(token: string): Promise<ConversationOut> {
  return apiFetch<ConversationOut>(`/api/conversations/invites/${token}/accept`, { method: 'POST' });
}

export function listMembers(conversationId: number): Promise<ConversationMemberOut[]> {
  return apiFetch<ConversationMemberOut[]>(`/api/conversations/${conversationId}/members`);
}

/** Pass your own user_id to leave; the owner can pass any other member's user_id to remove them. */
export function removeMember(conversationId: number, userId: number): Promise<void> {
  return apiFetch<void>(`/api/conversations/${conversationId}/members/${userId}`, { method: 'DELETE' });
}

export async function exportConversation(id: number, format: 'markdown' | 'json'): Promise<{ blob: Blob; filename: string }> {
  const resp = await apiFetchRaw(`/api/conversations/${id}/export?format=${format}`);
  const blob = await resp.blob();
  const disposition = resp.headers.get('Content-Disposition') || '';
  const match = disposition.match(/filename="([^"]+)"/);
  const filename = match ? match[1] : `conversation-${id}.${format === 'json' ? 'json' : 'md'}`;
  return { blob, filename };
}
