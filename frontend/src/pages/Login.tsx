import { FormEvent, useEffect, useState } from 'react';
import styles from './Login.module.css';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [accessCount, setAccessCount] = useState<string>('—');

  useEffect(() => {
    // Match body styles from static/login.html
    const prevMargin = document.body.style.margin;
    const prevOverflow = document.body.style.overflow;
    document.body.style.margin = '0';
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.margin = prevMargin;
      document.body.style.overflow = prevOverflow;
    };
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const r = await fetch('/api/login-stats');
        const d = await r.json();
        setAccessCount(((d.count as number) || 0).toLocaleString());
      } catch {
        setAccessCount('0');
      }
    })();
  }, []);

  async function doLogin(ev: FormEvent<HTMLFormElement>) {
    ev.preventDefault();
    setError('');
    try {
      const res = await fetch('/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim(), password }),
      });
      const body = await res.json();
      if (!res.ok || body.access_revoked) {
        setError(body.message || body.detail || 'Sign in failed.');
        return;
      }
      localStorage.setItem('sarmaan_token', body.access_token);
      localStorage.setItem(
        'sarmaan_user',
        JSON.stringify({
          role: body.role,
          name: body.name,
          email: body.email,
          permissions: body.permissions || [],
        })
      );
      window.location.href = '/';
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Sign in failed.';
      setError(msg);
    }
  }

  return (
    <div className={styles.body}>
      <div className={styles.shell}>
        {/* LEFT */}
        <aside className={styles.left}>
          <div className={styles.brandLogo}>
            <img src="/static/sarmaan_logo.jpg" alt="SARMAAN II" />
          </div>
          <h1 className={styles.brandTitle}>
            SARMAAN
            <br />
            Monitoring &amp; Tracking
            <br />
            Tool Dashboard
          </h1>
          <p className={styles.brandSubtitle}>
            Safety &amp; Antimicrobial Resistance
            <br />
            Mass Administration of Azithromycin
          </p>

          <div className={styles.roleList}>
            <div className={`${styles.roleCard} ${styles.roleSuperAdmin}`}>
              <span className={styles.dot}></span>
              <div>
                <h4>Super Admin</h4>
                <p>Full system access</p>
              </div>
            </div>
            <div className={`${styles.roleCard} ${styles.roleAdmin}`}>
              <span className={styles.dot}></span>
              <div>
                <h4>Admin</h4>
                <p>Dashboard &amp; validation</p>
              </div>
            </div>
            <div className={`${styles.roleCard} ${styles.roleValidator}`}>
              <span className={styles.dot}></span>
              <div>
                <h4>Validator</h4>
                <p>Assigned LGAs only</p>
              </div>
            </div>
            <div className={`${styles.roleCard} ${styles.rolePublic}`}>
              <span className={styles.dot}></span>
              <div>
                <h4>Public</h4>
                <p>Read-only view</p>
              </div>
            </div>
          </div>

          <div className={styles.leftFooter}>
            FMoH / SARMAAN Project &nbsp;&bull;&nbsp; Sokoto C3 &nbsp;&bull;&nbsp; 2026
            <br />
            Powered by{' '}
            <a href="https://ehealthafrica.org" target="_blank" rel="noopener noreferrer">
              eHealth Africa
            </a>
          </div>
        </aside>

        {/* RIGHT */}
        <main className={styles.right}>
          <h1 className={styles.welcome}>Welcome back</h1>
          <p className={styles.welcomeSub}>Sign in with your username to continue</p>

          <form onSubmit={doLogin}>
            <div className={styles.field}>
              <label htmlFor="email">Username or Email</label>
              <div className={styles.inputWrap}>
                <i className={`bi bi-person ${styles.pref}`}></i>
                <input
                  type="text"
                  id="email"
                  placeholder="username or email"
                  autoComplete="username"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>
            </div>
            <div className={styles.field}>
              <label htmlFor="password">Password</label>
              <div className={styles.inputWrap}>
                <i className={`bi bi-lock ${styles.pref}`}></i>
                <input
                  type={showPassword ? 'text' : 'password'}
                  id="password"
                  placeholder="••••••••"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
                <button
                  type="button"
                  className={styles.suf}
                  onClick={() => setShowPassword((s) => !s)}
                  aria-label="Toggle password visibility"
                >
                  <i className={showPassword ? 'bi bi-eye' : 'bi bi-eye-slash'}></i>
                </button>
              </div>
            </div>
            {error && <div className={styles.errorMsg}>{error}</div>}
            <button type="submit" className={styles.btnSignin}>
              <i className="bi bi-box-arrow-in-right"></i> Sign In
            </button>
          </form>

          <div className={styles.countPill}>
            <i className="bi bi-eye"></i> Dashboard accessed &nbsp;<strong>{accessCount}</strong>
            &nbsp; times
          </div>

          <div className={styles.links}>
            <a href="#">Terms of Use</a>
            <span className={styles.sep}>|</span>
            <a href="#">Privacy Policy</a>
          </div>
        </main>
      </div>
    </div>
  );
}
