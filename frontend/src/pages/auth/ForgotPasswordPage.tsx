import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { AuthLayout } from '../../components/layout/AuthLayout';
import { ApiError } from '../../api/client';
import * as authApi from '../../api/auth';

export function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setMessage(null);
    setSubmitting(true);
    try {
      const resp = await authApi.forgotPassword({ email });
      setMessage(resp.message);
    } catch (err) {
      if (err instanceof ApiError && err.status === 429) {
        setError('Too many attempts, try again shortly.');
      } else {
        setError(err instanceof Error ? err.message : 'Something went wrong');
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthLayout>
      <h2>Reset your password</h2>
      <div className="auth-subtitle">We'll email you a reset link if the account exists</div>
      {error && <div className="auth-error">{error}</div>}
      {message && <div className="auth-success">{message}</div>}
      <form onSubmit={handleSubmit}>
        <div className="auth-field">
          <label>Email</label>
          <input
            className="auth-input"
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        <button className="auth-submit" type="submit" disabled={submitting}>
          {submitting ? 'Sending…' : 'Send reset link'}
        </button>
      </form>
      <div className="auth-links">
        <Link to="/login">Back to sign in</Link>
        <span />
      </div>
    </AuthLayout>
  );
}
