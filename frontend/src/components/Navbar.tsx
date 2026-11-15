import React from 'react';
import { User } from '../api';
import { DocPilotLogo, LogOutIcon, ShieldIcon } from './icons';

interface NavbarProps {
  user: User | null;
  onLogout: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({ user, onLogout }) => {
  return (
    <header className="navbar">
      <div className="logo-group">
        <DocPilotLogo size={30} />
        <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.45rem' }}>
          <span style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--brand-navy)', letterSpacing: '-0.025em' }}>
            DocPilot
          </span>
          <span
            style={{
              fontSize: '0.68rem',
              fontWeight: 700,
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
              color: 'var(--brand-muted-blue)',
              background: 'var(--brand-muted-blue-subtle)',
              padding: '0.12rem 0.45rem',
              borderRadius: '4px',
              border: '1px solid #D6E3F0',
            }}
          >
            Enterprise
          </span>
        </div>
      </div>

      {user && (
        <div className="user-nav">
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.65rem',
              padding: '0.35rem 0.75rem',
              background: 'var(--bg-card-subtle)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-sm)',
            }}
          >
            <div
              style={{
                width: '26px',
                height: '26px',
                borderRadius: '50%',
                background: 'var(--brand-navy)',
                color: '#FFFFFF',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '0.75rem',
                fontWeight: 700,
              }}
            >
              {(user.full_name || user.email || 'U')[0].toUpperCase()}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.2 }}>
              <span style={{ fontSize: '0.825rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                {user.full_name || user.email}
              </span>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                {user.email}
              </span>
            </div>
            <span
              style={{
                fontSize: '0.68rem',
                fontWeight: 600,
                padding: '0.12rem 0.45rem',
                borderRadius: '4px',
                background: user.role === 'admin' ? 'var(--accent-brass-subtle)' : 'var(--bg-app)',
                color: user.role === 'admin' ? '#8C6734' : 'var(--text-secondary)',
                border: user.role === 'admin' ? '1px solid #E6D8C5' : '1px solid var(--border-subtle)',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.2rem',
                marginLeft: '0.25rem',
              }}
            >
              {user.role === 'admin' && <ShieldIcon size={11} />}
              {user.role}
            </span>
          </div>

          <button className="btn btn-secondary" onClick={onLogout} title="Logout" style={{ padding: '0.5rem 0.95rem' }}>
            <LogOutIcon size={15} />
            <span>Sign Out</span>
          </button>
        </div>
      )}
    </header>
  );
};
