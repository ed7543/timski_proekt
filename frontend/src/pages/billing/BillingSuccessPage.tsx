import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { AppShell } from '../../components/layout/AppShell';
import { CourseNavSidebar } from '../../components/courses/CourseNavSidebar';
import { useAuth } from '../../context/AuthContext';

/** Stripe redirects here after a successful Checkout. The webhook (server to
 * server, see backend/routes/billingRoute.py) is what actually flips
 * is_premium - it can land slightly after this page loads, so we poll
 * refreshUser a few times rather than assuming it's already true. */
export function BillingSuccessPage() {
  const { user, refreshUser } = useAuth();
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    let cancelled = false;
    let attempts = 0;

    const poll = async () => {
      await refreshUser();
      attempts += 1;
      if (cancelled) return;
      if (attempts >= 5) {
        setChecking(false);
        return;
      }
      setTimeout(poll, 1500);
    };
    poll();

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const isPremium = user?.is_premium;

  return (
    <AppShell sidebar={<CourseNavSidebar />}>
      <div className="body">
        <div className="page-container" style={{ maxWidth: 480 }}>
          <div className="page-header">
            <h1>{isPremium ? "You're premium!" : 'Payment received'}</h1>
            <p className="page-subtitle">
              {isPremium
                ? 'Your subscription is active - you can submit courses for review now.'
                : checking
                  ? 'Confirming your subscription with Stripe…'
                  : "This is taking longer than expected. Refresh the page in a bit - the webhook may still be processing."}
            </p>
          </div>
          {isPremium && (
            <Link to="/marketplace/submit" className="btn btn-primary" style={{ display: 'inline-block', marginTop: 12 }}>
              Submit a course
            </Link>
          )}
        </div>
      </div>
    </AppShell>
  );
}
