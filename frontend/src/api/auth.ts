import { apiFetch } from './client';
import type {
  RegisterRequest,
  LoginRequest,
  TokenResponse,
  CurrentUser,
  ForgotPasswordRequest,
  ResetPasswordRequest,
  MessageResponse,
} from '../types/auth';

export function register(payload: RegisterRequest): Promise<TokenResponse> {
  return apiFetch<TokenResponse>('/api/auth/register', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function login(payload: LoginRequest): Promise<TokenResponse> {
  return apiFetch<TokenResponse>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function logout(): Promise<MessageResponse> {
  return apiFetch<MessageResponse>('/api/auth/logout', { method: 'POST' });
}

export function me(): Promise<CurrentUser> {
  return apiFetch<CurrentUser>('/api/auth/me');
}

export function verifyEmail(token: string): Promise<MessageResponse> {
  return apiFetch<MessageResponse>(`/api/auth/verify-email?token=${encodeURIComponent(token)}`);
}

export function forgotPassword(payload: ForgotPasswordRequest): Promise<MessageResponse> {
  return apiFetch<MessageResponse>('/api/auth/forgot-password', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function resetPassword(payload: ResetPasswordRequest): Promise<MessageResponse> {
  return apiFetch<MessageResponse>('/api/auth/reset-password', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
