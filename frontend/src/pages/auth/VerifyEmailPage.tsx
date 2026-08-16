import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { AuthLayout } from '../../components/layout/AuthLayout';
import { ApiError } from '../../api/client';
import * as authApi from '../../api/auth';

export function VerifyEmailPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token') || '';
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading');
  const [message, setMessage] = useState('');

  useEffect(() => {
    if (!token) {
      setStatus('error');
      setMessage('No verification token found in the URL.');
      return;
    }
    authApi
      .verifyEmail(token)
      .then((resp) => {
        setStatus('success');
        setMessage(resp.message);
      })
      .catch((err) => {
        setStatus('error');
        setMessage(err instanceof ApiError ? err.message : 'Verification failed.');
      });
  }, [token]);

  return (
    <AuthLayout>
      <h2>Email verification</h2>
      {status === 'loading' && <div className="auth-subtitle">Verifying your email…</div>}
      {status === 'success' && <div className="auth-success">{message}</div>}
      {status === 'error' && <div className="auth-error">{message}</div>}
      <div className="auth-links">
        <Link to="/login">Back to sign in</Link>
        <span />
      </div>
    </AuthLayout>
  );
}
