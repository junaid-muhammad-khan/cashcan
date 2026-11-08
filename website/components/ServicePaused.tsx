"use client";

import Link from "next/link";
import { AppHeader } from "./AppChrome";
import "./ServicePaused.css";

/** Shown when the database is paused (for example its free daily limit is used up). Plain words, a retry, and the pages that still work. */
export function ServicePaused({ onRetry, message }: { onRetry?: () => void; message?: string }) {
  return (
    <section className="paused" role="alert" aria-labelledby="paused-h">
      <span className="paused-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round"><path d="M9 5v14M15 5v14" /></svg>
      </span>
      <h1 id="paused-h" className="paused-title">CashCan is paused for now</h1>
      <p className="paused-msg">
        {message ?? "CashCan's database isn't available right now, so we can't load this. It may be paused for the day (it has a free daily limit). Please try again later."}
      </p>
      <p className="paused-safe">Nothing is lost. Your account, face match and rewards are not affected.</p>
      <div className="paused-actions">
        {onRetry && <button type="button" className="btn btn-primary" onClick={onRetry}>Try again</button>}
        <Link href="/prices" className="btn btn-ghost">See prices</Link>
        <Link href="/" className="btn btn-ghost">Home</Link>
      </div>
    </section>
  );
}

/** The same notice as a whole signed-in page (with the app header), for pages that can't show anything without the database. */
export default function PausedScreen({ current, onRetry, message }: { current: "dashboard" | "profile" | "play"; onRetry?: () => void; message?: string }) {
  return (
    <div className="paused-page">
      <AppHeader current={current} />
      <main className="paused-main"><ServicePaused onRetry={onRetry} message={message} /></main>
    </div>
  );
}
