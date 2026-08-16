import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { GuestIcon } from '../icons';

export function UserFooter() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  if (user) {
    const initial = (user.full_name || user.email || '?')[0].toUpperCase();
    return (
      <div className="user-foot">
        <div className="avatar">
          <span style={{ fontFamily: "'Instrument Serif', serif", fontStyle: 'italic' }}>{initial}</span>
        </div>
        <div className="user-info">
          <div className="user-name">{user.full_name || user.email}</div>
          <div className="user-plan">
            {user.is_verified ? 'Verified' : 'Unverified'} ·{' '}
            <span
              className="logout-link"
              onClick={async () => {
                await logout();
                navigate('/login');
              }}
            >
              Log out
            </span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="user-foot">
      <div className="avatar">
        <GuestIcon />
      </div>
      <div className="user-info">
        <div className="user-name">Guest</div>
        <div className="user-plan">Not signed in</div>
      </div>
      <button className="login-btn" onClick={() => navigate('/login')}>
        Sign in
      </button>
    </div>
  );
}
