"use client";

import { useRef, useState } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useGSAP } from "@gsap/react";
import { Coin, Drop, Pin } from "./icons";
import "./ProblemStory.css";

gsap.registerPlugin(ScrollTrigger, useGSAP);

const CHAPTERS = [
  {
    key: "rules",
    title: "Your city's rules, not a material label",
    body: "Every decision is looked up against a local rule table, so the bin says where an item really goes in Metro Vancouver, and why.",
    tile: "#E3F5EB",
    Icon: Pin,
  },
  {
    key: "contamination",
    title: "Catches contamination",
    body: "A top camera and a front camera must agree. Food-soiled or greasy items are flagged and earn a reduced reward instead of slipping through.",
    tile: "#FBF1D8",
    Icon: Drop,
  },
  {
    key: "reward",
    title: "A reason to get it right",
    body: "Reward-eligible items pay out instantly to your Solana wallet. The hauler that buys the sorted material funds the rewards.",
    tile: "#E4EEF8",
    Icon: Coin,
  },
];

/**
 * "The problem" as interactive storytelling: on desktop the section pins and scroll scrubs
 * through three scenes (city rules -> contamination -> reward). Cards fill as you go and
 * clicking one jumps to its scene. Phones and reduced-motion get a static stacked layout
 * with every scene in its finished state.
 */
export default function ProblemStory() {
  const root = useRef<HTMLElement>(null);
  const stRef = useRef<ScrollTrigger | null>(null);
  const [active, setActive] = useState(0);

  useGSAP(
    () => {
      const q = gsap.utils.selector(root);
      const mm = gsap.matchMedia();

      mm.add("(min-width: 1000px) and (prefers-reduced-motion: no-preference)", () => {
        root.current?.classList.add("ps-live");
        const scenes = q<HTMLElement>(".ps-scene");
        gsap.set(scenes.slice(1), { autoAlpha: 0, y: 30 });

        // Initial (pre-animation) states, all reversible because the timeline is scrubbed.
        gsap.set(q(".ps-stamp"), { autoAlpha: 0, scale: 2.2, rotate: -22 });
        gsap.set(q(".ps-rule"), { autoAlpha: 0, x: -30 });
        gsap.set(q(".ps-tag-old"), { opacity: 1 });
        gsap.set(q(".ps-scanline"), { y: 0 });
        gsap.set(q(".ps-spot"), { fill: "#E9E3D6", scale: 0.6, transformOrigin: "50% 50%" });
        gsap.set(q(".ps-camframe"), { opacity: 0.35 });
        gsap.set(q(".ps-flag"), { autoAlpha: 0, y: 14 });
        gsap.set(q(".ps-item"), { y: -90, autoAlpha: 0 });
        gsap.set(q(".ps-coin"), { autoAlpha: 0, x: 0, y: 0, scale: 0.6 });
        gsap.set(q(".ps-fund"), { autoAlpha: 0, y: 12 });
        gsap.set(q(".ps-bar i"), { scaleX: 0 });

        const amount = q<HTMLElement>(".ps-amount")[0];
        const counter = { v: 0 };
        if (amount) amount.textContent = "+0.0000";

        const tl = gsap.timeline({ defaults: { ease: "none" } });
        // ---- scene 1: the label lies, the stamp tells the truth
        tl.to(q(".ps-bar i")[0], { scaleX: 1, duration: 1 }, 0)
          .to(q(".ps-stamp"), { autoAlpha: 1, scale: 1, rotate: -8, ease: "back.out(2)", duration: 0.3 }, 0.25)
          .to(q(".ps-tag-old"), { opacity: 0.35, duration: 0.2 }, 0.35)
          .to(q(".ps-rule"), { autoAlpha: 1, x: 0, stagger: 0.12, ease: "power2.out", duration: 0.3 }, 0.55)
          // ---- to scene 2
          .to(scenes[0], { autoAlpha: 0, y: -30, duration: 0.15 }, 0.92)
          .to(scenes[1], { autoAlpha: 1, y: 0, duration: 0.15 }, 1.0)
          .to(q(".ps-bar i")[1], { scaleX: 1, duration: 1 }, 1)
          .to(q(".ps-camframe"), { opacity: 1, stagger: 0.08, duration: 0.15 }, 1.1)
          .to(q(".ps-scanline"), { y: 170, ease: "sine.inOut", duration: 0.45 }, 1.2)
          .to(q(".ps-spot"), { fill: "#E3B23C", scale: 1, stagger: 0.05, ease: "back.out(2)", duration: 0.2 }, 1.4)
          .to(q(".ps-flag"), { autoAlpha: 1, y: 0, ease: "power2.out", duration: 0.2 }, 1.7)
          // ---- to scene 3
          .to(scenes[1], { autoAlpha: 0, y: -30, duration: 0.15 }, 1.92)
          .to(scenes[2], { autoAlpha: 1, y: 0, duration: 0.15 }, 2.0)
          .to(q(".ps-bar i")[2], { scaleX: 1, duration: 1 }, 2)
          .to(q(".ps-item"), { y: 0, autoAlpha: 1, ease: "power2.in", duration: 0.25 }, 2.1)
          .to(q(".ps-coin"), { autoAlpha: 1, scale: 1, duration: 0.08 }, 2.35)
          .to(q(".ps-coin"), { x: 200, ease: "power1.inOut", duration: 0.35 }, 2.38)
          .to(q(".ps-coin"), { keyframes: { y: [0, -110, 4], ease: "sine.inOut" }, duration: 0.35 }, 2.38)
          .to(q(".ps-coin"), { scale: 0.4, autoAlpha: 0, duration: 0.06 }, 2.72)
          .to(counter, {
            v: 0.004, duration: 0.25,
            onUpdate: () => { if (amount) amount.textContent = `+${counter.v.toFixed(4)}`; },
          }, 2.7)
          .to(q(".ps-wallet"), { scale: 1.04, yoyo: true, repeat: 1, duration: 0.06 }, 2.72)
          .to(q(".ps-fund"), { autoAlpha: 1, y: 0, ease: "power2.out", duration: 0.2 }, 2.78);

        const st = ScrollTrigger.create({
          trigger: root.current,
          start: "top top",
          end: "+=240%",
          pin: true,
          scrub: 0.6,
          animation: tl,
          onUpdate: (self) => setActive(Math.min(2, Math.floor(self.progress * 3 * 0.999))),
        });
        stRef.current = st;

        // Ambient: the background blobs drift on their own, and the stage leans toward the pointer.
        q<HTMLElement>(".ps-blob").forEach((b, i) =>
          gsap.to(b, { x: i ? -60 : 70, y: i ? 40 : -50, scale: 1.15, duration: 9 + i * 3, ease: "sine.inOut", repeat: -1, yoyo: true }),
        );
        const stage = q<HTMLElement>(".ps-stage-card")[0];
        const rx = gsap.quickTo(stage, "rotationX", { duration: 0.6, ease: "power3.out" });
        const ry = gsap.quickTo(stage, "rotationY", { duration: 0.6, ease: "power3.out" });
        const onMove = (e: PointerEvent) => {
          const r = stage.getBoundingClientRect();
          ry(((e.clientX - r.left) / r.width - 0.5) * 8);
          rx(-((e.clientY - r.top) / r.height - 0.5) * 8);
        };
        const onLeave = () => { rx(0); ry(0); };
        stage.addEventListener("pointermove", onMove);
        stage.addEventListener("pointerleave", onLeave);

        return () => {
          stage.removeEventListener("pointermove", onMove);
          stage.removeEventListener("pointerleave", onLeave);
          stRef.current = null;
          root.current?.classList.remove("ps-live");
        };
      });

      // Phones / reduced motion: no pin, no scrub. Just reveal each chapter as it arrives.
      mm.add("(max-width: 999px) and (prefers-reduced-motion: no-preference)", () => {
        q<HTMLElement>(".ps-chapter-mobile").forEach((el) =>
          gsap.from(el, { y: 30, autoAlpha: 0, duration: 0.7, ease: "power3.out", scrollTrigger: { trigger: el, start: "top 88%", once: true } }),
        );
      });

      return () => mm.revert();
    },
    { scope: root },
  );

  // Clicking a card scrolls to the middle of its chapter (desktop) so its scene plays.
  const goTo = (i: number) => {
    const st = stRef.current;
    setActive(i);
    if (!st) return;
    const y = st.start + ((i + 0.55) / 3) * (st.end - st.start);
    window.scrollTo({ top: y, behavior: "smooth" });
  };

  return (
    <section className="section ps" id="rules" ref={root} aria-labelledby="ps-h">
      <div aria-hidden="true" className="ps-blob ps-blob-a" />
      <div aria-hidden="true" className="ps-blob ps-blob-b" />
      <div className="container ps-grid">
        <div className="ps-copy">
          <div className="eyebrow">The problem</div>
          <h2 id="ps-h">One greasy container can ruin a whole batch of recycling.</h2>
          <p className="section-lede">
            Sorting rules are local and confusing, smart bins classify material instead of what your city accepts,
            and there is little reason for anyone to get it right. CashCan fixes all three at the bin.
          </p>
          <ol className="ps-cards">
            {CHAPTERS.map((c, i) => (
              <li key={c.key}>
                <button type="button" className={`ps-card${active === i ? " on" : ""}`} aria-current={active === i ? "step" : undefined} onClick={() => goTo(i)}>
                  <span className="icon-tile" style={{ background: c.tile }}><c.Icon /></span>
                  <span className="ps-card-text">
                    <b>{c.title}</b>
                    <small>{c.body}</small>
                  </span>
                  <span className="ps-bar" aria-hidden="true"><i /></span>
                </button>
              </li>
            ))}
          </ol>
        </div>

        <div className="ps-stage" aria-hidden="true">
          <div className="ps-stage-card">
            <div className="ps-stage-top">
              <span>{["01 · Local rules", "02 · Contamination", "03 · Reward"][active]}</span>
              <span className="ps-dots">{[0, 1, 2].map((i) => <i key={i} className={i <= active ? "on" : undefined} />)}</span>
            </div>

            {/* scene 1: compostable cup, stamped by the local rule */}
            <div className="ps-scene ps-chapter-mobile">
              <span className="ps-mobile-label">01 · Local rules</span>
              <svg viewBox="0 0 420 300" className="ps-svg">
                <ellipse cx="150" cy="262" rx="70" ry="8" fill="#0F1F17" opacity=".08" />
                <path d="M100 70h100l-14 190h-72z" fill="#F7F3EA" stroke="#C9C1AE" strokeWidth="2" />
                <rect x="92" y="56" width="116" height="18" rx="6" fill="#E9E3D6" stroke="#C9C1AE" strokeWidth="2" />
                <path d="M118 120c10 18 54 18 64 0" fill="none" stroke="#C9C1AE" strokeWidth="3" strokeLinecap="round" />
                <g className="ps-tag-old">
                  <rect x="104" y="150" width="92" height="30" rx="6" fill="#2BB673" />
                  <text x="150" y="170" textAnchor="middle" fontSize="12" fontWeight="700" fill="#fff" letterSpacing="1">COMPOSTABLE</text>
                </g>
                <g className="ps-stamp" style={{ transformOrigin: "160px 168px" }}>
                  <rect x="74" y="140" width="172" height="56" rx="8" fill="none" stroke="#B4321F" strokeWidth="4" />
                  <text x="160" y="166" textAnchor="middle" fontSize="15" fontWeight="800" fill="#B4321F" letterSpacing="1.5">GARBAGE</text>
                  <text x="160" y="185" textAnchor="middle" fontSize="10" fontWeight="700" fill="#B4321F" letterSpacing="1">IN VANCOUVER</text>
                </g>
                <g fontSize="11" fill="#33433A">
                  <g className="ps-rule"><rect x="240" y="96" width="172" height="34" rx="8" fill="#fff" stroke="#DCE4DD" /><text x="254" y="117">Label says: compostable</text></g>
                  <g className="ps-rule"><rect x="240" y="140" width="172" height="34" rx="8" fill="#fff" stroke="#DCE4DD" /><text x="254" y="161">Local rule: garbage</text></g>
                  <g className="ps-rule"><rect x="240" y="184" width="172" height="34" rx="8" fill="#E3F5EB" stroke="#9BD9B6" /><text x="254" y="205" fill="#0E5A33" fontWeight="700">Bin: Waste, and why</text></g>
                </g>
              </svg>
            </div>

            {/* scene 2: two cameras scan a greasy tray */}
            <div className="ps-scene ps-chapter-mobile">
              <span className="ps-mobile-label">02 · Contamination</span>
              <svg viewBox="0 0 420 300" className="ps-svg">
                <defs>
                  <clipPath id="ps-scan-clip"><rect x="60" y="40" width="300" height="200" rx="14" /></clipPath>
                </defs>
                <rect x="60" y="40" width="300" height="200" rx="14" fill="#14211A" />
                <g className="ps-camframe"><rect x="72" y="52" width="80" height="20" rx="5" fill="#24402F" /><text x="112" y="66" textAnchor="middle" fontSize="10" fill="#8FB5A0" letterSpacing="1">TOP CAM</text></g>
                <g className="ps-camframe"><rect x="268" y="52" width="80" height="20" rx="5" fill="#24402F" /><text x="308" y="66" textAnchor="middle" fontSize="10" fill="#8FB5A0" letterSpacing="1">FRONT CAM</text></g>
                <path d="M120 120h180l-18 82H138z" fill="#F7F3EA" stroke="#C9C1AE" strokeWidth="2" />
                <path d="M112 116h196" stroke="#C9C1AE" strokeWidth="6" strokeLinecap="round" />
                <circle className="ps-spot" cx="168" cy="150" r="10" />
                <circle className="ps-spot" cx="210" cy="172" r="14" />
                <circle className="ps-spot" cx="252" cy="148" r="8" />
                <circle className="ps-spot" cx="236" cy="186" r="6" />
                <g clipPath="url(#ps-scan-clip)">
                  <g className="ps-scanline"><rect x="60" y="54" width="300" height="2" fill="#5FD79A" /><rect x="60" y="38" width="300" height="18" fill="#5FD79A" opacity=".12" /></g>
                </g>
                <rect x="132" y="108" width="158" height="102" rx="6" fill="none" stroke="#5FD79A" strokeWidth="2" strokeDasharray="6 5" />
                <g className="ps-flag">
                  <rect x="100" y="250" width="220" height="36" rx="18" fill="#FBF1D8" />
                  <circle cx="122" cy="268" r="5" fill="#E3B23C" />
                  <text x="136" y="272" fontSize="12" fontWeight="700" fill="#7A4F00">Contaminated · reward 25%</text>
                </g>
              </svg>
            </div>

            {/* scene 3: item in, coin out to the wallet */}
            <div className="ps-scene ps-chapter-mobile">
              <span className="ps-mobile-label">03 · Reward</span>
              <svg viewBox="0 0 420 300" className="ps-svg">
                <g>
                  <path d="M60 120h110l-12 140H72z" fill="#157A46" />
                  <path d="M52 112h126" stroke="#0E5A33" strokeWidth="10" strokeLinecap="round" />
                  <path d="M100 160c8-8 22-8 30 0M115 156v44" stroke="#fff" strokeWidth="5" fill="none" strokeLinecap="round" />
                </g>
                <g className="ps-item"><ellipse cx="115" cy="86" rx="16" ry="5" fill="#9FB3A8" /><rect x="99" y="56" width="32" height="30" rx="4" fill="#C7D3CC" /><ellipse cx="115" cy="56" rx="16" ry="5" fill="#E6EEE9" /></g>
                <g className="ps-coin" style={{ transformOrigin: "115px 110px" }}>
                  <circle cx="115" cy="110" r="16" fill="#E3B23C" stroke="#B5832F" strokeWidth="3" />
                  <text x="115" y="115" textAnchor="middle" fontSize="13" fontWeight="800" fill="#7A4F00">◎</text>
                </g>
                <g className="ps-wallet" style={{ transformOrigin: "330px 150px" }}>
                  <rect x="236" y="96" width="176" height="108" rx="16" fill="#0F1F17" />
                  <text x="254" y="124" fontSize="11" fill="#8FB5A0">Your wallet · devnet</text>
                  <text x="254" y="164" fontSize="26" fontWeight="800" fill="#5FD79A" className="ps-amount">+0.0040</text>
                  <text x="254" y="188" fontSize="11" fill="#B9C7BF">SOL · aluminum can</text>
                </g>
                <g className="ps-fund">
                  <rect x="196" y="236" width="214" height="40" rx="12" fill="#E4EEF8" />
                  <text x="210" y="261" fontSize="11.5" fill="#2C5F8A" fontWeight="600">Funded by the hauler that buys it</text>
                </g>
              </svg>
            </div>
          </div>
          <p className="ps-note">Illustration. Local rules are examples and must be checked against your city&apos;s program.</p>
        </div>
      </div>
    </section>
  );
}
