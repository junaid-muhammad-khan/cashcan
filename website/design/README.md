# CashCan home page design

Source of the scroll-animated home page designed in Claude's design canvas:
https://claude.ai/artifact/TkYWfdG7fJxha1xG49K4ga (private until shared from its Share menu).

- `Main.dc.html` — the page (Design Component format: HTML markup plus a small logic class)
- `Login.dc.html`, `Signup.dc.html`, `Dashboard.dc.html` — log-in, sign-up and signed-in dashboard screens
- `canvas.json` — the canvas index

What it includes: scroll-triggered reveals, hero mockup that untilts on scroll, floating
cards and a live drop feed, animated gradient background, count-up numbers, a sticky
five-step "how it works" story, and a dashboard preview that expands on scroll. Honors
`prefers-reduced-motion`. Feed and dashboard figures are sample values, labelled as such.

This is a design reference, not the production site. Suggested build stack:
Next.js + Tailwind + GSAP ScrollTrigger / Framer Motion.
