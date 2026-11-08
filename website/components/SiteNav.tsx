"use client";

import Link from "next/link";
import { useAuth0 } from "@auth0/auth0-react";
import { Logo } from "./icons";

export default function SiteNav() {
  const { isAuthenticated, isLoading, logout } = useAuth0();

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
        {isLoading ? null : isAuthenticated ? (
          <>
            <Link href="/account" className="btn btn-dark">Your account</Link>
            <button
              type="button"
              className="text-link"
              onClick={() => logout({ logoutParams: { returnTo: window.location.origin } })}
            >
              Log out
            </button>
          </>
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
