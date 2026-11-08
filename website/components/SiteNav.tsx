import Link from "next/link";
import { Logo } from "./icons";

export default function SiteNav({ signedInName }: { signedInName?: string | null }) {
  return (
    <nav className="nav container" aria-label="Main">
      <Link href="/" className="logo">
        <Logo />
        <span>cashcan</span>
      </Link>
      <div className="nav-links">
        <a href="/#how">How it works</a>
        <a href="/#rules">Local rules</a>
        <a href="/#dashboard">Dashboard</a>
        <a href="/#privacy">Privacy</a>
      </div>
      <div className="nav-actions">
        {signedInName ? (
          <Link href="/account" className="btn btn-dark">Your account</Link>
        ) : (
          <>
            <Link href="/login" className="text-link">Log in</Link>
            <Link href="/signup" className="btn btn-dark">Sign up</Link>
          </>
        )}
      </div>
    </nav>
  );
}
