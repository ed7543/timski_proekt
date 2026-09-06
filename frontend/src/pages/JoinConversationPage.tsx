import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { acceptInvite } from '../api/conversations';
import { ApiError } from '../api/client';

/** Handles its own auth check rather than being wrapped in ProtectedRoute,
 * so it can redirect to /login with `state.from` pointing back here
 * (LoginPage already supports this - see its `from` var - nothing else in
 * the app currently uses it) instead of losing the invite token. */
export function JoinConversationPage() {
  const { token } = useParams<{ token: string }>();
  const navigate = useNavigate();
  const { status } = useAuth();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (status === 'loading' || !token) return;
    if (status === 'unauthenticated') {
      navigate('/login', { state: { from: `/chat/join/${token}` }, replace: true });
      return;
    }
    acceptInvite(token)
      .then((conv) => navigate(`/chat/${conv.id}`, { replace: true }))
      .catch((err) => {
        if (err instanceof ApiError && err.status === 410) {
          setError('This invite link has expired or been revoked.');
        } else if (err instanceof ApiError && err.status === 409) {
          setError('This conversation already has its maximum number of members.');
        } else if (err instanceof ApiError && err.status === 404) {
          setError('This invite link is invalid.');
        } else {
          setError(err instanceof Error ? err.message : 'Could not join this conversation.');
        }
      });
  }, [status, token, navigate]);

  return (
    <div className="auth-shell">
      {error ? (
        <div className="auth-error" style={{ maxWidth: 400 }}>{error}</div>
      ) : (
        <span style={{ color: 'var(--muted)', fontSize: 13 }}>Joining conversation…</span>
      )}
    </div>
  );
}
