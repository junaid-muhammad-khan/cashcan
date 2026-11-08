"use client";

import Link from "next/link";
import { useAuth0 } from "@auth0/auth0-react";
import { LogoMark } from "@/components/icons";

// Header and footer for the signed-in app pages (dashboard and profile), so they look like one product. They use the
// `.db` styles from app/dashboard/dashboard.css, so the page must be wrapped in <div className="db"> and import that CSS.
const S = { stroke: "#fff", fill: "none", strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true };

export function AppHeader({ current }: { current: "dashboard" | "profile" }) {
  const { logout } = useAuth0();
  const cur = (k: string) => (k === current ? ({ "aria-current": "page" } as const) : {});
  return (
    <header className="db-top">
      <Link href="/" className="db-logo">
        <span className="db-logo-mark">
          <svg {...S} width={22} height={22} viewBox="0 0 32 32" strokeWidth={2.6}>
            <path d="M7 9h18l-2 18H9z" /><path d="M5 9h22" /><path d="M12 9V6h8v3" /><path d="M13 15c1.5-1.5 4.5-1.5 6 0M16 14v8" />
          </svg>
        </span>
        <span>cashcan</span>
      </Link>
      <nav aria-label="Account" className="db-top-links">
        <Link href="/" className="db-pill">Home</Link>
        <Link href="/dashboard" className={`db-pill${current === "dashboard" ? " is-current" : ""}`} {...cur("dashboard")}>Dashboard</Link>
        {current === "dashboard" && <a href="#redeem" className="db-pill">Redeem</a>}
        <Link href="/account" className={`db-pill${current === "profile" ? " is-current" : ""}`} {...cur("profile")}>Profile</Link>
        <button type="button" className="db-pill" onClick={() => logout({ logoutParams: { returnTo: window.location.origin } })}>Log out</button>
      </nav>
    </header>
  );
}

export function AppFooter({ note }: { note: string }) {
  return (
    <footer className="db-footer">
      <span className="db-footer-brand"><LogoMark size={18} />Cashcan · Thoughtful sorting, one item at a time.</span>
      <span>{note}</span>
    </footer>
  );
}
