import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

export default function DashboardPlaceholder() {
  const navigate = useNavigate();

  useEffect(() => {
    const token = localStorage.getItem('sarmaan_token');
    if (!token) {
      navigate('/login', { replace: true });
      return;
    }
    // Route to the legacy vanilla dashboard until Phase 2 migrates it.
    window.location.href = '/dashboard-legacy';
  }, [navigate]);

  return (
    <div
      style={{
        height: '100vh',
        width: '100vw',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontFamily: "'Inter', system-ui, sans-serif",
        color: '#64748b',
        background: '#052e1d',
      }}
    >
      <div style={{ color: '#e8f5ee', fontSize: 14 }}>Loading dashboard…</div>
    </div>
  );
}
