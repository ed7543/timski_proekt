import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { AuthLayout } from '../../components/layout/AuthLayout';
import { ApiError } from '../../api/client';
import * as authApi from '../../api/auth';

export function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token') || '';
  const [password, setPassword] = useState('');
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setMessage(null);
    if (!token) {
      setError('Missing or invalid reset token.');
      return;
    }
    setSubmitting(true);
    try {
      const resp = await authApi.resetPassword({ token, new_password: password });
      setMessage(resp.message + ' Redirecting to sign in…');
      setTimeout(() => navigate('/login'), 1500);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message || 'Invalid or expired token.');
      } else {
        setError(err instanceof Error ? err.message : 'Something went wrong');
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthLayout>
      <h2>Choose a new password</h2>
      <div className="auth-subtitle">Enter a new password for your account</div>
      {!token && <div className="auth-error">No reset token found in the URL - use the link from your email.</div>}
      {error && <div className="auth-error">{error}</div>}
      {message && <div className="auth-success">{message}</div>}
      <form onSubmit={handleSubmit}>
        <div className="auth-field">
          <label>New password</label>
          <input
            className="auth-input"
            type="password"
            required
            minLength={6}
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        <button className="auth-submit" type="submit" disabled={submitting || !token}>
          {submitting ? 'Saving…' : 'Reset password'}
        </button>
      </form>
      <div className="auth-links">
        <Link to="/login">Back to sign in</Link>
        <span />
      </div>
    </AuthLayout>
  );
}
