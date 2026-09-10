import { useEffect, useState } from 'react';
import { AppShell } from '../components/layout/AppShell';
import { CourseNavSidebar } from '../components/courses/CourseNavSidebar';
import { useAuth } from '../context/AuthContext';
import { listPlans, createCheckoutSession, cancelSubscription } from '../api/billing';
import type { BillingPlan } from '../api/billing';

function formatPrice(plan: BillingPlan): string {
  const amount = (plan.price_cents / 100).toFixed(2);
  const symbol = plan.currency.toLowerCase() === 'eur' ? '€' : plan.currency.toUpperCase() + ' ';
  const suffix = plan.interval ? `/${plan.interval}` : '';
  return `${symbol}${amount}${suffix}`;
}

function PlanCard({ plan }: { plan: BillingPlan }) {
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubscribe = async () => {
    setError(null);
    setStarting(true);
    try {
      const { checkout_url } = await createCheckoutSession();
      window.location.href = checkout_url;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start checkout');
      setStarting(false);
    }
  };

  return (
    <div className="plan-card">
      <div className="plan-card-head">
        <div className="plan-name">{plan.name}</div>
        <div className="plan-price">{formatPrice(plan)}</div>
      </div>
      {plan.description && <p className="plan-desc">{plan.description}</p>}
      <p className="plan-desc">Lets you submit courses to the Marketplace, with materials attached.</p>
      {error && <div className="auth-error" style={{ marginTop: 8 }}>{error}</div>}
      <button type="button" className="btn btn-primary" style={{ marginTop: 12 }} disabled={starting} onClick={handleSubscribe}>
        {starting ? 'Redirecting…' : 'Subscribe'}
      </button>
    </div>
  );
}

/** Dedicated plan-picker page - separate from the submit-course form's wall,
 * so "become a contributor" (user footer) and the Marketplace's upsell both
 * land somewhere that's actually about choosing/buying a subscription. Only
 * one plan exists today, but this renders whatever GET /api/billing/plans
 * returns, so adding a second plan later is a backend-only change. */
export function SubscribePage() {
  const { user, refreshUser } = useAuth();
  const [plans, setPlans] = useState<BillingPlan[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);

  useEffect(() => {
    listPlans()
      .then((data) => {
        setPlans(data);
        setError(null);
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load plans'));
  }, []);

  const alreadyUnlocked = user?.is_premium || user?.role === 'admin';

  const handleCancel = async () => {
    if (!window.confirm('Cancel your subscription? This takes effect immediately.')) return;
    setError(null);
    setCancelling(true);
    try {
      await cancelSubscription();
      await refreshUser();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to cancel subscription');
    } finally {
      setCancelling(false);
    }
  };

  return (
    <AppShell sidebar={<CourseNavSidebar />}>
      <div className="body">
        <div className="page-container" style={{ maxWidth: 560 }}>
          <div className="page-header">
            <h1>Subscribe</h1>
            <p className="page-subtitle">Choose a plan to unlock course submission.</p>
          </div>

          {alreadyUnlocked && (
            <div className="empty" style={{ marginTop: 24 }}>
              <p style={{ margin: 0 }}>
                {user?.role === 'admin' && !user.is_premium
                  ? "You're an admin, so you can already submit courses without a subscription."
                  : "You're subscribed - you can submit courses any time."}
              </p>
              {error && <div className="auth-error" style={{ marginTop: 12 }}>{error}</div>}
              {user?.is_premium && (
                <button
                  type="button"
                  className="btn btn-danger"
                  style={{ marginTop: 12 }}
                  disabled={cancelling}
                  onClick={handleCancel}
                >
                  {cancelling ? 'Cancelling…' : 'Cancel subscription'}
                </button>
              )}
            </div>
          )}

          {!alreadyUnlocked && error && <div className="msg-error" style={{ marginTop: 20 }}>{error}</div>}

          {!alreadyUnlocked && plans === null && !error && (
            <div className="empty" style={{ marginTop: 24 }}>Loading plans…</div>
          )}

          {!alreadyUnlocked && plans !== null && plans.length === 0 && !error && (
            <div className="empty" style={{ marginTop: 24 }}>
              Subscriptions aren't configured on this server yet.
            </div>
          )}

          {!alreadyUnlocked && plans !== null && plans.length > 0 && (
            <div style={{ marginTop: 24, display: 'flex', flexDirection: 'column', gap: 12 }}>
              {plans.map((plan) => (
                <PlanCard key={plan.id} plan={plan} />
              ))}
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
