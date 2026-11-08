"use client";

import Link from "next/link";
import { useRef } from "react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";
import { Check, LogoMark } from "./icons";

gsap.registerPlugin(useGSAP);

/** Default side-panel content: a payout card and a sample weekly-earnings card. */
function DefaultAside() {
  return (
    <div className="aside-cards">
      <div className="float-card">
        <span className="ok-dot"><Check size={18} color="#0F1F17" strokeWidth={3} /></span>
        <span><b style={{ fontSize: 14 }}>Payout sent</b><small>+0.004 SOL · aluminum can · devnet</small></span>
      </div>
      <div className="float-card week-card">
        <div className="week-head"><span>This week</span><span>sample</span></div>
        <div className="week-amount">0.031 SOL</div>
        <div className="week-sub">from 14 clean drops</div>
      </div>
    </div>
  );
}

export default function AuthShell({
  heading,
  body,
  aside,
  wide,
  children,
}: {
  heading: React.ReactNode;
  body: string;
  aside?: React.ReactNode;
  wide?: boolean;
  children: React.ReactNode;
}) {
  const root = useRef<HTMLDivElement>(null);

  useGSAP(
    () => {
      const mm = gsap.matchMedia();
      mm.add("(prefers-reduced-motion: no-preference)", () => {
        gsap.from("[data-intro]", { y: 24, autoAlpha: 0, duration: 0.7, ease: "power3.out", stagger: 0.07 });
        gsap.from(".auth-aside .float-card, .journey li", { y: 30, autoAlpha: 0, scale: 0.94, duration: 0.8, ease: "back.out(1.6)", stagger: 0.12, delay: 0.3 });
        gsap.utils.toArray<HTMLElement>(".auth-aside .float-card").forEach((c, i) =>
          gsap.to(c, { y: i % 2 ? 10 : -10, duration: 3.2 + i, ease: "sine.inOut", repeat: -1, yoyo: true, delay: 1.2 + i * 0.6 }),
        );
        gsap.utils.toArray<HTMLElement>(".auth-aside .blob").forEach((b, i) =>
          gsap.to(b, { x: i ? -70 : 80, y: i ? 50 : -40, scale: 1.15, duration: 10 + i * 3, ease: "sine.inOut", repeat: -1, yoyo: true }),
        );
      });
      return () => mm.revert();
    },
    { scope: root },
  );

  return (
    <div className="auth" ref={root}>
      <aside className="auth-aside">
        <div aria-hidden="true" className="blob" style={{ width: 420, height: 420, background: "#2BB673", opacity: 0.3, left: -120, top: -80 }} />
        <div aria-hidden="true" className="blob" style={{ width: 360, height: 360, background: "#E3B23C", opacity: 0.2, right: -100, bottom: -80 }} />
        <Link href="/" className="logo" style={{ position: "relative" }}><LogoMark /><span>cashcan</span></Link>
        <div className="auth-aside-body">
          <h2 data-intro>{heading}</h2>
          <p data-intro>{body}</p>
          {aside ?? <DefaultAside />}
        </div>
      </aside>
      <main className="auth-main">
        <div className={wide ? "auth-card wide" : "auth-card"}>
          <Link href="/" className="logo auth-top"><LogoMark /><span>cashcan</span></Link>
          {children}
        </div>
      </main>
    </div>
  );
}
