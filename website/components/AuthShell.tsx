"use client";

import Link from "next/link";
import { useRef } from "react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";
import { Check, Logo } from "./icons";

gsap.registerPlugin(useGSAP);

export default function AuthShell({
  heading,
  body,
  children,
}: {
  heading: string;
  body: string;
  children: React.ReactNode;
}) {
  const root = useRef<HTMLDivElement>(null);

  useGSAP(
    () => {
      const mm = gsap.matchMedia();
      mm.add("(prefers-reduced-motion: no-preference)", () => {
        gsap.from("[data-intro]", { y: 24, autoAlpha: 0, duration: 0.7, ease: "power3.out", stagger: 0.07 });
        gsap.from(".float-card", { y: 30, autoAlpha: 0, scale: 0.94, duration: 0.8, ease: "back.out(1.6)", delay: 0.35 });
        gsap.to(".float-card", { y: -10, duration: 3.2, ease: "sine.inOut", repeat: -1, yoyo: true, delay: 1.2 });
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
        <Link href="/" className="logo" style={{ position: "relative" }}><Logo color="#5FD79A" /><span>cashcan</span></Link>
        <div className="auth-aside-body">
          <h2 data-intro>{heading}</h2>
          <p data-intro>{body}</p>
          <div className="float-card">
            <span style={{ width: 36, height: 36, borderRadius: "50%", background: "#2BB673", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
              <Check size={18} color="#0F1F17" strokeWidth={3} />
            </span>
            <span><b style={{ fontSize: 14 }}>Payout sent</b><small>+0.004 SOL · aluminum can · devnet</small></span>
          </div>
        </div>
      </aside>
      <main className="auth-main">
        <div className="auth-card">
          <Link href="/" className="logo auth-top"><Logo /><span>cashcan</span></Link>
          {children}
        </div>
      </main>
    </div>
  );
}
