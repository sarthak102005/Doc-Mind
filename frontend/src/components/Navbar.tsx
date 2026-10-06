import React from 'react';
import { User } from '../api';
import { LogOutIcon, ShieldIcon } from './icons';

interface NavbarProps {
  user: User | null;
  onLogout: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({ user, onLogout }) => {
  return (
    <header className="navbar">
      <div className="logo-group">
        <span className="logo-badge">DM</span>
        <span>DocMind</span>
      </div>

      {user && (
        <div className="user-nav">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.875rem' }}>
            <span style={{ color: 'var(--text-muted)' }}>{user.full_name || user.email}</span>
            <span
              style={{
                fontSize: '0.7rem',
                padding: '0.15rem 0.45rem',
                borderRadius: '4px',
                background: user.role === 'admin' ? 'rgba(99, 102, 241, 0.2)' : 'rgba(255, 255, 255, 0.1)',
                color: user.role === 'admin' ? '#a5b4fc' : 'var(--text-dim)',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.25rem',
              }}
            >
              {user.role === 'admin' && <ShieldIcon size={12} />}
              {user.role}
            </span>
          </div>

          <button className="btn btn-secondary" onClick={onLogout} title="Logout" style={{ padding: '0.45rem 0.85rem' }}>
            <LogOutIcon size={16} />
            <span>Logout</span>
          </button>
        </div>
      )}
    </header>
  );
};
