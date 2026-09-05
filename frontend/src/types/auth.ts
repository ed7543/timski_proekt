export interface RegisterRequest {
  email: string;
  password: string;
  full_name?: string | null;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export type UserRole = 'student' | 'admin';

export interface CurrentUser {
  id: number;
  email: string;
  full_name: string | null;
  is_verified: boolean;
  role: UserRole;
  is_premium: boolean;
  // Separate from is_premium so a user who submitted a Marketplace course
  // and later cancelled their subscription still sees "My courses" in the
  // nav - is_premium alone would hide their own submission history.
  has_submitted_courses: boolean;
}

export interface ForgotPasswordRequest {
  email: string;
}

export interface ResetPasswordRequest {
  token: string;
  new_password: string;
}

export interface MessageResponse {
  message: string;
}
