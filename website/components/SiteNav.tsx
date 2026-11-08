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
        <Link href="/how-it-works">How it works</Link>
        <Link href="/local-rules">Local rules</Link>
        <Link href="/prices">Prices</Link>
        <Link href="/privacy">Privacy</Link>
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
