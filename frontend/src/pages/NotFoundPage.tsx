import { Link } from 'react-router-dom';

export function NotFoundPage() {
  return (
    <div className="app paper-grain" style={{ flexDirection: 'column' }}>
      <div className="stub-page">
        <h2>404</h2>
        <p>This page doesn't exist.</p>
        <Link to="/chat" className="login-btn" style={{ marginTop: 8, display: 'inline-block' }}>
          Back to chat
        </Link>
      </div>
    </div>
  );
}
