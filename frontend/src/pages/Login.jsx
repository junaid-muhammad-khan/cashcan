export default function Login({ info }) {
  return (
    <div className="center">
      <div className="card login">
        <h1>CashCan</h1>
        <p className="muted">Sort it right. Get paid.</p>
        <a className="btn primary" href="/auth/login">Sign up / Sign in</a>
        {info.dev_login && (
          <>
            <a className="btn ghost" href="/auth/dev-login">Dev login: demo user (with data)</a>
            <a className="btn ghost" href="/auth/dev-login?user=new">Dev login: new user (try onboarding)</a>
            <p className="tiny muted">Auth0 isn't configured, so the dev login is on. Set AUTH0_* in backend/.env to switch.</p>
          </>
        )}
      </div>
    </div>
  );
}
