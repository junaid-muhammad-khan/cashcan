"use client";

import { useRef, useState } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useGSAP } from "@gsap/react";
import { Coin, Pin } from "./icons";
import "./ProblemStory.css";

gsap.registerPlugin(ScrollTrigger, useGSAP);

// Canada's waste sent to disposal (landfill + incineration) in 2022: Statistics Canada, summarized by madeinca.ca.
const SOURCE_URL = "https://madeinca.ca/recycling-canada-statistics/";
const TONS_MILLION = 26.6;
const BEARS = 27; // one polar-bear icon per ~1 million (26.6 rounds to 27 icons, the last one partly filled)

const BinIcon = () => (
  <svg width="22" height="22" viewBox="0 0 32 32" fill="none" stroke="#2C5F8A" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M7 9h18l-2 18H9z" /><path d="M5 9h22" /><path d="M12 9V6h8v3" /><path d="M13 15c1.5-1.5 4.5-1.5 6 0M16 14v8" />
  </svg>
);

const CHAPTERS = [
  {
    key: "scale",
    title: "26.6 million tonnes thrown away",
    body: "In 2022 Canada recycled or composted only about 27% of its waste. A record 26.6 million tonnes went to landfill or incineration, and plenty of it could have been recycled.",
    tile: "#E4EEF8",
    Icon: BinIcon,
  },
  {
    key: "track",
    title: "A bin that tracks every item",
    body: "Two cameras see what you're holding and your city's rules say which container it belongs in, so it goes in the right one, every time.",
    tile: "#E3F5EB",
    Icon: Pin,
  },
  {
    key: "cash",
    title: "Cash back for getting it right",
    body: "Put a recyclable in the right container and the reward pays out instantly to your Solana wallet. Recycling right finally pays.",
    tile: "#FBF1D8",
    Icon: Coin,
  },
];

// A small polar bear facing right: body, head with snout and ear, four legs. Drawn in a 44x26 box.
const BEAR_PATH =
  "M3 15C3 9 8 6 15 6H26C29 6 31 5 33 4L36 3C38 3 39 4 40 5L42 8C43 9 43 10 42 11L40 11.5L37 12L35 13V22H32V17H30V22H27V16H18V22H15V17H13V22H10V17H8V22H5V17C3.5 16.5 3 16 3 15Z";
const Bear = ({ fill, clip }: { fill: string; clip?: string }) => (
  <g clipPath={clip}>
    <path d={BEAR_PATH} fill={fill} />
    <circle cx="36.5" cy="3.2" r="1.6" fill={fill} />
  </g>
);

/**
 * "The problem" as interactive storytelling. Desktop: the section pins and scroll scrubs
 * three scenes (the scale of misplaced recycling -> a bin that tracks each item -> cash back).
 * Cards fill as you go; clicking one jumps to its scene. Phones, reduced motion and no-JS
 * get a static stacked layout with every scene in its finished state.
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

        // Scene 1 start state
        const bears = q<SVGElement>(".ps-bear");
        gsap.set(bears, { autoAlpha: 0.12, scale: 0.7, transformOrigin: "50% 50%" });
        gsap.set(q(".ps-bear-fill"), { autoAlpha: 0.12 });
        gsap.set(q(".ps-weigh"), { autoAlpha: 0, y: 10 });
        const tons = q<HTMLElement>(".ps-tons")[0];
        const t = { v: 0 };
        if (tons) tons.textContent = "0.0";
        // Scene 2 start state
        gsap.set(q(".ps-item2"), { x: -120, y: -40, autoAlpha: 0 });
        gsap.set(q(".ps-track"), { x: -120, y: -40, autoAlpha: 0 });
        gsap.set(q(".ps-binhl"), { autoAlpha: 0 });
        gsap.set(q(".ps-verdict"), { autoAlpha: 0, y: 12 });
        // Scene 3 start state
        gsap.set(q(".ps-item"), { y: -90, autoAlpha: 0 });
        gsap.set(q(".ps-coin"), { autoAlpha: 0, x: 0, y: 0, scale: 0.6 });
        gsap.set(q(".ps-bar i"), { scaleX: 0 });
        const amount = q<HTMLElement>(".ps-amount")[0];
        const cash = { v: 0 };
        if (amount) amount.textContent = "+0.0000";

        const tl = gsap.timeline({ defaults: { ease: "none" } });
        // ---- scene 1: the number climbs, the bears fill in, one per million tons
        tl.to(q(".ps-bar i")[0], { scaleX: 1, duration: 1 }, 0)
          .to(t, { v: TONS_MILLION, duration: 0.6, onUpdate: () => { if (tons) tons.textContent = t.v.toFixed(1); } }, 0.08)
          .to(bears.slice(0, BEARS - 1), { autoAlpha: 1, scale: 1, stagger: 0.02, ease: "back.out(2)", duration: 0.1 }, 0.1)
          .to(bears[BEARS - 1], { autoAlpha: 1, scale: 1, duration: 0.1 }, 0.62)
          .to(q(".ps-bear-fill"), { autoAlpha: 1, duration: 0.05 }, 0.66)
          .to(q(".ps-weigh"), { autoAlpha: 1, y: 0, ease: "power2.out", duration: 0.2 }, 0.7)
          // ---- to scene 2: the item is tracked to the right container
          .to(scenes[0], { autoAlpha: 0, y: -30, duration: 0.15 }, 0.92)
          .to(scenes[1], { autoAlpha: 1, y: 0, duration: 0.15 }, 1.0)
          .to(q(".ps-bar i")[1], { scaleX: 1, duration: 1 }, 1)
          .to([q(".ps-item2"), q(".ps-track")], { autoAlpha: 1, duration: 0.08 }, 1.1)
          .to([q(".ps-item2"), q(".ps-track")], { x: 0, y: 0, ease: "power1.inOut", duration: 0.35 }, 1.12)
          .to(q(".ps-binhl"), { autoAlpha: 1, duration: 0.1 }, 1.45)
          .to(q(".ps-item2"), { y: 70, autoAlpha: 0, ease: "power2.in", duration: 0.2 }, 1.55)
          .to(q(".ps-track"), { autoAlpha: 0, duration: 0.1 }, 1.55)
          .to(q(".ps-verdict"), { autoAlpha: 1, y: 0, ease: "power2.out", duration: 0.2 }, 1.68)
          // ---- to scene 3: cash back
          .to(scenes[1], { autoAlpha: 0, y: -30, duration: 0.15 }, 1.92)
          .to(scenes[2], { autoAlpha: 1, y: 0, duration: 0.15 }, 2.0)
          .to(q(".ps-bar i")[2], { scaleX: 1, duration: 1 }, 2)
          .to(q(".ps-item"), { y: 0, autoAlpha: 1, ease: "power2.in", duration: 0.25 }, 2.1)
          .to(q(".ps-coin"), { autoAlpha: 1, scale: 1, duration: 0.08 }, 2.35)
          .to(q(".ps-coin"), { x: 200, ease: "power1.inOut", duration: 0.35 }, 2.38)
          .to(q(".ps-coin"), { keyframes: { y: [0, -110, 4], ease: "sine.inOut" }, duration: 0.35 }, 2.38)
          .to(q(".ps-coin"), { scale: 0.4, autoAlpha: 0, duration: 0.06 }, 2.72)
          .to(cash, { v: 0.004, duration: 0.25, onUpdate: () => { if (amount) amount.textContent = `+${cash.v.toFixed(4)}`; } }, 2.7)
          .to(q(".ps-wallet"), { scale: 1.04, yoyo: true, repeat: 1, duration: 0.06 }, 2.72);

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

        // Ambient: drifting background blobs and a slight pointer tilt on the stage.
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

      mm.add("(max-width: 999px) and (prefers-reduced-motion: no-preference)", () => {
        q<HTMLElement>(".ps-chapter-mobile").forEach((el) =>
          gsap.from(el, { y: 30, autoAlpha: 0, duration: 0.7, ease: "power3.out", scrollTrigger: { trigger: el, start: "top 88%", once: true } }),
        );
      });

      return () => mm.revert();
    },
    { scope: root },
  );

  const goTo = (i: number) => {
    const st = stRef.current;
    setActive(i);
    if (!st) return;
    const y = st.start + ((i + 0.6) / 3) * (st.end - st.start);
    window.scrollTo({ top: y, behavior: "smooth" });
  };

  const cols = 9;
  return (
    <section className="section ps" id="rules" ref={root} aria-labelledby="ps-h">
      <div aria-hidden="true" className="ps-blob ps-blob-a" />
      <div aria-hidden="true" className="ps-blob ps-blob-b" />
      <div className="container ps-grid">
        <div className="ps-copy">
          <div className="eyebrow">The problem</div>
          <h2 id="ps-h">Canada threw away a record 26.6 million tonnes in 2022.</h2>
          <p className="section-lede">
            That&apos;s heavier than 26.6 million polar bears, and plenty of it could have been recycled. CashCan is a smart
            bin that tracks what you throw away, shows you the right container, and pays you cash back when you get it right.
          </p>
          <p className="ps-source">
            Source: Statistics Canada 2022 data, via <a href={SOURCE_URL} target="_blank" rel="noopener noreferrer">madeinca.ca</a>
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
              <span>{["01 · The scale", "02 · Tracked to the right bin", "03 · Cash back"][active]}</span>
              <span className="ps-dots">{[0, 1, 2].map((i) => <i key={i} className={i <= active ? "on" : undefined} />)}</span>
            </div>

            {/* scene 1: 26.6 million tons, one polar bear per million */}
            <div className="ps-scene ps-chapter-mobile">
              <span className="ps-mobile-label">01 · The scale</span>
              <svg viewBox="0 0 420 300" className="ps-svg">
                <text x="30" y="70" fontSize="52" fontWeight="800" fill="#0F1F17" letterSpacing="-2" fontFamily="var(--font-display)">
                  <tspan className="ps-tons">26.6</tspan><tspan fontSize="30" dx="4">M tonnes</tspan>
                </text>
                <text x="32" y="96" fontSize="13" fill="#4A5A51">of waste sent to landfill or incineration in Canada, 2022</text>
                <g>
                  {Array.from({ length: BEARS }, (_, i) => {
                    const x = 30 + (i % cols) * 40, y = 120 + Math.floor(i / cols) * 34;
                    const last = i === BEARS - 1;
                    return (
                      <g key={i} transform={`translate(${x} ${y})`}>
                        <g className="ps-bear" transform="scale(0.86)">
                          {last ? (
                            <>
                              <defs><clipPath id="ps-bear-clip"><rect x="0" y="0" width={44 * 0.6} height="26" /></clipPath></defs>
                              <Bear fill="#DCE4DD" />
                              <g className="ps-bear-fill"><Bear fill="#8CC6E8" clip="url(#ps-bear-clip)" /></g>
                            </>
                          ) : (
                            <Bear fill="#8CC6E8" />
                          )}
                        </g>
                      </g>
                    );
                  })}
                </g>
                <g className="ps-weigh">
                  <rect x="30" y="232" width="360" height="40" rx="12" fill="#E4EEF8" />
                  <text x="46" y="257" fontSize="12.5" fill="#2C5F8A" fontWeight="700">Heavier than 26.6 million polar bears</text>
                  <text x="374" y="257" fontSize="11" fill="#2C5F8A" textAnchor="end">1 bear ≈ 1M</text>
                </g>
              </svg>
            </div>

            {/* scene 2: the bin tracks the item and points it to the right container */}
            <div className="ps-scene ps-chapter-mobile">
              <span className="ps-mobile-label">02 · Tracked to the right bin</span>
              <svg viewBox="0 0 420 300" className="ps-svg">
                {/* camera bar */}
                <rect x="60" y="22" width="300" height="26" rx="13" fill="#0F1F17" />
                <circle cx="78" cy="35" r="6" fill="#5FD79A" /><circle cx="342" cy="35" r="6" fill="#5FD79A" />
                <text x="210" y="39" textAnchor="middle" fontSize="10" fill="#8FB5A0" letterSpacing="1">TOP + FRONT CAMERA</text>
                {/* three containers */}
                {[
                  { x: 50, label: "Cans", color: "#157A46" },
                  { x: 165, label: "Organics", color: "#A06E00" },
                  { x: 280, label: "Waste", color: "#5C6B62" },
                ].map((b) => (
                  <g key={b.label}>
                    <path d={`M${b.x} 170h90l-10 100h-70z`} fill={b.color} opacity={b.label === "Cans" ? 1 : 0.35} />
                    <rect x={b.x - 6} y="160" width="102" height="12" rx="6" fill={b.color} opacity={b.label === "Cans" ? 1 : 0.35} />
                    <text x={b.x + 45} y="230" textAnchor="middle" fontSize="12" fontWeight="700" fill="#fff">{b.label}</text>
                  </g>
                ))}
                <rect className="ps-binhl" x="40" y="152" width="122" height="126" rx="14" fill="none" stroke="#5FD79A" strokeWidth="4" />
                {/* the item, travelling toward Cans, with its tracking box */}
                <g className="ps-item2"><rect x="80" y="86" width="30" height="40" rx="5" fill="#C7D3CC" /><rect x="80" y="86" width="30" height="8" rx="3" fill="#E6EEE9" /></g>
                <g className="ps-track">
                  <rect x="70" y="76" width="50" height="60" rx="6" fill="none" stroke="#5FD79A" strokeWidth="2" strokeDasharray="5 4" />
                  <rect x="70" y="60" width="78" height="14" rx="4" fill="#5FD79A" /><text x="75" y="70.5" fontSize="9" fontWeight="700" fill="#0F1F17">CAN · 0.94</text>
                </g>
                <g className="ps-verdict">
                  <rect x="186" y="96" width="196" height="40" rx="12" fill="#E3F5EB" />
                  <text x="200" y="121" fontSize="12.5" fill="#0E5A33" fontWeight="700">Aluminum can → Cans ✓</text>
                </g>
              </svg>
            </div>

            {/* scene 3: item in, coin out to the wallet */}
            <div className="ps-scene ps-chapter-mobile">
              <span className="ps-mobile-label">03 · Cash back</span>
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
              </svg>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
