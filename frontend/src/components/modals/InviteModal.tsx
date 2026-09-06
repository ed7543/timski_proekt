import { useEffect, useState } from 'react';
import { ModalShell } from './ModalShell';
import { createInvite, listMembers, removeMember } from '../../api/conversations';
import type { ConversationMemberOut, ConversationInviteOut } from '../../types/conversation';
import { TrashIcon } from '../icons';

interface Props {
  conversationId: number;
  isOwner: boolean;
  /** From the backend's ConversationDetailOut.max_members - not hardcoded here, so this can't silently drift out of sync with the server's actual cap. */
  maxMembers: number;
  onClose: () => void;
  /** Called after a member is removed (or the viewer leaves) so ChatPage can refresh. */
  onMembersChanged: () => void;
}

export function InviteModal({ conversationId, isOwner, maxMembers, onClose, onMembersChanged }: Props) {
  const [members, setMembers] = useState<ConversationMemberOut[]>([]);
  const [invite, setInvite] = useState<ConversationInviteOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listMembers(conversationId)
      .then((m) => {
        if (!cancelled) setMembers(m);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load members');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [conversationId]);

  const handleCreateInvite = async () => {
    setCreating(true);
    setError(null);
    try {
      const created = await createInvite(conversationId);
      setInvite(created);
      setCopied(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create invite link');
    } finally {
      setCreating(false);
    }
  };

  const handleCopy = async () => {
    if (!invite) return;
    try {
      await navigator.clipboard.writeText(invite.url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // clipboard API unavailable/denied - the link is still visible to copy manually
    }
  };

  const handleRemove = async (userId: number) => {
    setError(null);
    try {
      await removeMember(conversationId, userId);
      setMembers((prev) => prev.filter((m) => m.user_id !== userId));
      onMembersChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to remove member');
    }
  };

  const atCapacity = members.length >= maxMembers;

  return (
    <ModalShell onClose={onClose} maxWidth={440}>
      <h2>Invite to this chat</h2>
      <div className="modal-subtitle">Up to {maxMembers} people can chat together here</div>

      {loading ? (
        <div className="empty">Loading…</div>
      ) : (
        <>
          <ol className="src-list">
            {members.map((m) => (
              <li key={m.user_id}>
                <div className="src">
                  <div className="src-row">
                    <div className="src-body">
                      <div className="src-title">
                        {m.name}
                        {m.is_owner && ' (owner)'}
                      </div>
                    </div>
                    {isOwner && !m.is_owner && (
                      <button
                        type="button"
                        className="thread-action-btn danger"
                        aria-label={`Remove ${m.name}`}
                        onClick={() => handleRemove(m.user_id)}
                      >
                        <TrashIcon />
                      </button>
                    )}
                  </div>
                </div>
              </li>
            ))}
          </ol>

          {isOwner && (
            <div style={{ marginTop: 16 }}>
              {atCapacity ? (
                <div className="empty">This conversation already has {maxMembers} members.</div>
              ) : invite ? (
                <div className="material-row">
                  <div className="material-row-fields">
                    <input className="auth-input" type="text" readOnly value={invite.url} style={{ flex: 1 }} />
                    <button type="button" className="modal-close ghost" onClick={handleCopy}>
                      {copied ? 'Copied!' : 'Copy'}
                    </button>
                  </div>
                </div>
              ) : (
                <button type="button" className="login-btn" disabled={creating} onClick={handleCreateInvite}>
                  {creating ? 'Creating…' : 'Create invite link'}
                </button>
              )}
            </div>
          )}

          {error && <div className="auth-error" style={{ marginTop: 12 }}>{error}</div>}
        </>
      )}

      <div className="modal-footer">
        <div />
        <button className="modal-close" onClick={onClose}>
          Close
        </button>
      </div>
    </ModalShell>
  );
}
