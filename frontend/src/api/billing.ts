import { apiFetch } from './client';

export interface BillingPlan {
  id: string;
  name: string;
  description: string | null;
  price_cents: number;
  currency: string;
  interval: string | null;
}

/** Available subscription plans - just one right now, but the /subscribe
 * page renders whatever this returns so more can be added later without a
 * frontend change. Empty array means Stripe isn't configured yet. */
export function listPlans(): Promise<BillingPlan[]> {
  return apiFetch<BillingPlan[]>('/api/billing/plans');
}

/** Starts a Stripe Checkout session for the course-submission subscription.
 * Redirect the browser to the returned checkout_url. */
export function createCheckoutSession(): Promise<{ checkout_url: string }> {
  return apiFetch<{ checkout_url: string }>('/api/billing/checkout', { method: 'POST' });
}

/** Cancels the current user's course-submission subscription immediately.
 * Call refreshUser() (AuthContext) afterwards so user.is_premium updates in the UI. */
export function cancelSubscription(): Promise<{ is_premium: boolean }> {
  return apiFetch<{ is_premium: boolean }>('/api/billing/cancel', { method: 'POST' });
}

/** Starts a one-time Stripe Checkout session to unlock a single priced
 * course's materials/recordings. Redirect the browser to checkout_url. */
export function createCourseCheckoutSession(courseId: number): Promise<{ checkout_url: string }> {
  return apiFetch<{ checkout_url: string }>(`/api/billing/courses/${courseId}/checkout`, { method: 'POST' });
}
