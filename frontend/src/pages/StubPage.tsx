import { Link } from 'react-router-dom';

export function StubPage({ title, description }: { title: string; description: string }) {
  return (
    <div className="app paper-grain" style={{ flexDirection: 'column' }}>
      <div className="stub-page">
        <h2>{title}</h2>
        <p>{description}</p>
        <Link to="/chat" className="login-btn" style={{ marginTop: 8, display: 'inline-block' }}>
          Back to chat
        </Link>
      </div>
    </div>
  );
}
