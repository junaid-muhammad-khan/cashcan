"use client";

import Link from "next/link";
import { useAuth0 } from "@auth0/auth0-react";
import { LogoMark } from "./icons";
import { AppHeader } from "./AppChrome";

export default function SiteNav() {
  const { isAuthenticated, isLoading } = useAuth0();

  // Signed in: the same header as the dashboard and profile pages, so it does not change from page to page.
  if (!isLoading && isAuthenticated) return <AppHeader current="home" />;

  return (
    <nav className="nav container" aria-label="Main">
      <Link href="/" className="logo">
        <LogoMark />
        <span>cashcan</span>
      </Link>
      <div className="nav-links">
        <a href="/#how">How it works</a>
        <a href="/#rules">Local rules</a>
        <a href="/#privacy">Privacy</a>
      </div>
      <div className="nav-actions">
        {isLoading ? null : (

          <>
            <Link href="/login" className="text-link">Log in</Link>
            <Link href="/signup" className="btn btn-dark">Sign up</Link>
          </>
        )}
      </div>
    </nav>
  );
}
