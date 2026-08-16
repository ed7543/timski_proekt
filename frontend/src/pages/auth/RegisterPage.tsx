import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { AuthLayout } from '../../components/layout/AuthLayout';
import { useAuth } from '../../context/AuthContext';
import { ApiError } from '../../api/client';
import * as authApi from '../../api/auth';

export function RegisterPage() {
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const { loginWithToken } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const { access_token } = await authApi.register({
        email,
        password,
        full_name: fullName.trim() || null,
      });
      await loginWithToken(access_token);
      navigate('/chat', { replace: true });
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
      <h2>Create your account</h2>
      <div className="auth-subtitle">Sign up to save your progress</div>
      {error && <div className="auth-error">{error}</div>}
      <form onSubmit={handleSubmit}>
        <div className="auth-field">
          <label>Full name (optional)</label>
          <input
            className="auth-input"
            type="text"
            autoComplete="name"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
          />
        </div>
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
        <div className="auth-field">
          <label>Password</label>
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
        <button className="auth-submit" type="submit" disabled={submitting}>
          {submitting ? 'Creating account…' : 'Create account'}
        </button>
      </form>
      <div className="auth-links">
        <span />
        <Link to="/login">Already have an account? Sign in</Link>
      </div>
    </AuthLayout>
  );
}
