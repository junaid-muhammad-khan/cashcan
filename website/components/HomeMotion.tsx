"use client";

import { useRef } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useGSAP } from "@gsap/react";

gsap.registerPlugin(ScrollTrigger, useGSAP);

/**
 * All home-page motion lives here so the sections themselves stay server-rendered.
 * Content is fully visible without JS; every tween is a `from` or a reversible scrub,
 * and anything that moves is skipped for prefers-reduced-motion.
 */
export default function HomeMotion({ children }: { children: React.ReactNode }) {
  const root = useRef<HTMLDivElement>(null);

  useGSAP(
    () => {
      const q = gsap.utils.selector(root);
      const mm = gsap.matchMedia();

      // ---- Story: works for everyone; motion only when allowed ----
      const steps = q<HTMLElement>(".step");
      const scenes = q<HTMLElement>(".scene");
      const progress = q<HTMLElement>(".story-progress i")[0];
      const label = q<HTMLElement>("[data-step-label]")[0];
      let current = 0;
      const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      const showStep = (i: number) => {
        if (i === current && steps[i]?.classList.contains("active")) return;
        const dir = i > current ? 1 : -1;
        steps.forEach((s, j) => s.classList.toggle("active", j === i));
        scenes.forEach((s, j) => {
          if (j === i) {
            gsap.fromTo(s, { autoAlpha: 0, y: reduce ? 0 : 28 * dir, scale: reduce ? 1 : 0.97 },
              { autoAlpha: 1, y: 0, scale: 1, duration: reduce ? 0 : 0.55, ease: "power3.out", overwrite: true });
          } else {
            gsap.to(s, { autoAlpha: 0, y: reduce ? 0 : -24 * dir, duration: reduce ? 0 : 0.35, ease: "power2.in", overwrite: true });
          }
        });
        if (progress) gsap.to(progress, { scaleX: (i + 1) / steps.length, duration: reduce ? 0 : 0.5, ease: "power2.out" });
        if (label) label.textContent = `Step ${i + 1} of ${steps.length}`;
        current = i;
      };
      gsap.set(scenes, { autoAlpha: 0 });
      showStep(0);
      steps.forEach((step, i) =>
        ScrollTrigger.create({
          trigger: step,
          start: "top 60%",
          end: "bottom 60%",
          onEnter: () => showStep(i),
          onEnterBack: () => showStep(i),
        }),
      );

      // ---- Count-up numbers (instant for reduced motion) ----
      q<HTMLElement>("[data-count]").forEach((el) => {
        const target = Number(el.dataset.count);
        const suffix = el.dataset.suffix ?? "";
        if (reduce) { el.textContent = `${target}${suffix}`; return; }
        const obj = { v: 0 };
        el.textContent = `0${suffix}`;
        gsap.to(obj, {
          v: target,
          duration: 1.6,
          ease: "power3.out",
          scrollTrigger: { trigger: el, start: "top 85%", once: true },
          onUpdate: () => { el.textContent = `${Math.round(obj.v)}${suffix}`; },
        });
      });

      mm.add("(prefers-reduced-motion: no-preference)", () => {
        // Hero intro, staggered
        gsap.from(q("[data-intro]"), { y: 32, autoAlpha: 0, duration: 0.9, ease: "power3.out", stagger: 0.08, delay: 0.1 });
        gsap.from(q(".float"), { y: 24, autoAlpha: 0, scale: 0.92, duration: 0.8, ease: "back.out(1.6)", stagger: 0.15, delay: 0.6 });

        // Ambient background: drifting gradient blobs + floating cards
        q<HTMLElement>(".blob").forEach((b, i) => {
          gsap.to(b, {
            x: gsap.utils.random(-90, 90), y: gsap.utils.random(-60, 60), scale: gsap.utils.random(0.85, 1.2),
            duration: gsap.utils.random(9, 14), ease: "sine.inOut", repeat: -1, yoyo: true, delay: i * 0.6,
          });
        });
        q<HTMLElement>(".float").forEach((f, i) => {
          gsap.to(f, { y: i % 2 ? 12 : -14, duration: 3 + i, ease: "sine.inOut", repeat: -1, yoyo: true, delay: 1.4 });
        });

        // Hero mockup untilts and lifts as you scroll past it
        gsap.fromTo(q(".mock"), { rotateX: 14 }, {
          rotateX: 0, y: -20, ease: "none",
          scrollTrigger: { trigger: q(".hero")[0], start: "top top", end: "+=520", scrub: 0.6 },
        });

        // Generic scroll reveals, batched so siblings stagger together
        gsap.set(q("[data-reveal]"), { autoAlpha: 0 });
        ScrollTrigger.batch(q("[data-reveal]"), {
          start: "top 88%",
          once: true,
          onEnter: (els) => gsap.fromTo(els, { y: 40, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: 0.8, ease: "power3.out", stagger: 0.1 }),
        });

        gsap.set(q("[data-pop]"), { autoAlpha: 0 });
        ScrollTrigger.batch(q("[data-pop]"), {
          start: "top 90%",
          once: true,
          onEnter: (els) => gsap.fromTo(els, { y: 16, scale: 0.88, autoAlpha: 0 }, { y: 0, scale: 1, autoAlpha: 1, duration: 0.7, ease: "back.out(1.7)", stagger: 0.12 }),
        });

        gsap.from(q("[data-slide-left]"), {
          x: -48, autoAlpha: 0, duration: 0.9, ease: "power3.out",
          scrollTrigger: { trigger: q("[data-slide-left]")[0], start: "top 85%", once: true },
        });

        // Dashboard preview expands as it comes into view, then its charts grow
        const dash = q(".dash")[0];
        if (dash) {
          gsap.fromTo(dash, { scale: 0.88, y: 40 }, {
            scale: 1, y: 0, ease: "none",
            scrollTrigger: { trigger: dash, start: "top 95%", end: "top 35%", scrub: 0.5 },
          });
          const tl = gsap.timeline({ scrollTrigger: { trigger: dash, start: "top 60%", once: true } });
          tl.from(q(".bar-col"), { scaleY: 0, duration: 0.9, ease: "power3.out", stagger: 0.04 })
            .from(q(".hbar .track i"), { scaleX: 0, duration: 0.9, ease: "power3.out", stagger: 0.08 }, "<0.2");
        }

        // CTA blobs drift with scroll for a little depth
        q<HTMLElement>(".cta .blob").forEach((b, i) => {
          gsap.to(b, { yPercent: i ? -30 : 30, ease: "none", scrollTrigger: { trigger: ".cta", start: "top bottom", end: "bottom top", scrub: true } });
        });
      });

      return () => mm.revert();
    },
    { scope: root },
  );

  return <div ref={root}>{children}</div>;
}
