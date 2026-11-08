# CashCan

**Smart sorting bins that know your city's rules, and pay you for sorting correctly.**

> Hackathon project (24 hours). Theme: solve a problem in this world.
> Status: in progress. The Solana payout backend (`backend/`) is built and verified end-to-end; everything else below is still the plan, not a finished build.

---

## The problem

People sort waste wrong, and contamination ruins whole batches of recycling and compost.

- Sorting rules are local and confusing. In Metro Vancouver, an item labelled "compostable" may not be accepted in the green bin. Food-soiled paper and foodware cause confusion.
- Existing smart bins mostly classify by **material** (plastic, paper, metal, glass), not by **what your city actually accepts**.
- Image classifiers that score 95%+ on benchmarks often fail on real, contaminated items, and no public dataset of contaminated recyclables exists (per a June 2026 preprint).
- Signage and outreach reduce contamination but do not eliminate it. There is little immediate reason for a person to get it right.

## Our idea

A bin with a camera and sensor that:

1. Identifies the item and decides the correct bin **by local Metro Vancouver rules**, not just by material.
2. Detects **contamination** (for example, a greasy container).
3. Uses **two cameras (one on top, one on the front)** to look at the item from two angles, so detection is more reliable and harder to fool.
4. **Rewards** the user with a small crypto payout depending on what the item is detected as (which items earn a reward, and how much, is defined in the reward table below).
5. Logs everything to a dashboard, so we can show where and what people get wrong.

**Our edge:** local-rule-aware plus contamination-aware sorting, tied to an incentive. We searched and found no product doing exactly this. That is a search result, not proof that none exists.

---

## How it works

```
Register user
   -> Facial registration (enroll face, link it to the user's account)
   -> Connect Solana wallet
   -> At the bin: face match identifies the user
   -> Two cameras (top + front) capture the item
   -> Classifier (item + local rule + contamination)
   -> Reward table decides which items earn a payout
   -> Payout (devnet SOL)
   -> Activity log / dashboard
   -> (loops back for the next item)
```

### Reward table
The classifier detects the item, then a lookup table decides whether it earns a reward.
- Reward-eligible item, clean: payout.
- Reward-eligible item, contaminated: reduced or no payout.
- Item that earns no reward: no payout, but the bin still tells the user where it goes.
- Which items are reward-eligible and the exact amounts: **TBD** (the whiteboard note "Payout SOL by Classifier / 2" needs to be defined by the team).

### Anti-abuse (required, judges will ask)
- Rate limit per user per time window.
- Minimum classifier confidence before any payout.
- Reject repeated identical items in quick succession.
- Top and front camera detections must agree before a payout is issued.
- Face match must succeed before a payout. Add a basic liveness check (reject a face shown on a photo or screen) if time allows. If not, state that limit openly.

---

## Scope

### Must have (MVP)
- [ ] Classifier covering about 12 tricky Metro Vancouver items, clean and contaminated
- [ ] Local rule lookup table (item -> correct bin + reason)
- [ ] Two cameras (top and front) + Raspberry Pi capturing each item
- [ ] Bin indicator (LEDs or display) showing the correct bin and why
- [x] Reward table + devnet SOL payout for reward-eligible items — backend built and verified end-to-end (reward lookup, contamination multiplier, confidence gate, per-user cooldown, real signed transfer); see `backend/README.md`. Reward amounts in the table are still placeholders (see Open questions)
- [ ] Facial registration and face match at the bin, so each payout goes to the right user's wallet (opt-in consent screen, store face embeddings only, never raw photos, delete on request)
- [x] Activity log to Databricks (Delta table). `backend/src/activityLog.ts` writes each payout decision (paid or rejected) to `workspace.cashcan.activity_log` via the Databricks SQL Statement API, wired into the payout CLI; gated on `DATABRICKS_SERVER_HOSTNAME`/`DATABRICKS_HTTP_PATH`/`DATABRICKS_TOKEN` in `.env` and never throws (a Databricks hiccup must not block a real payout). Verified end-to-end against the live workspace (Free Edition, Serverless Starter Warehouse) — a real row round-tripped. The AI/BI **dashboard** on top of this table is not yet built; do that once there's more than a couple of seed rows
- [ ] Gemini API: generate the plain-language "why" text and auto-label photos to speed up data collection

### Nice to have (only if time remains)
- [ ] Simple user account page with payout history
- [ ] Short in-app walkthrough

### Cut for the 24-hour build
- Real money and the $ -> SOL -> $ conversion loop. Demo on **Solana devnet** with free test tokens only. Mock the conversion in the pitch.

---

## Proposed tech stack (not locked)

| Area | Proposed |
|---|---|
| Face recognition | Existing open-source library (for example face_recognition, InsightFace, or DeepFace). Store embeddings only, not photos |
| Vision model | Small model such as YOLOv8n or MobileNet, fine-tuned on our own photos |
| Edge device | Raspberry Pi with two cameras (top + front; placement TBD by hardware team) |
| Backend | Node / TypeScript — see `backend/` |
| Payout | Solana **devnet** — see `backend/` (Node/TypeScript, `@solana/web3.js`); demoing against a local `solana-test-validator` for reliability, see `backend/README.md` |
| Dashboard | Web app, data in Databricks (Free Edition: Delta table + AI/BI dashboard). `workspace.cashcan.activity_log` table live and receiving rows via `backend/src/activityLog.ts`; the AI/BI dashboard view itself not yet built |
| Gemini API | Plain-language "why this bin" explanations (English / Cantonese / Mandarin) and auto-labeling of our photo dataset. Keep the local model as the main classifier path, so the demo never depends on venue wifi |
| Domain | cashcan.com (set). See the domain note under "Awards we're targeting" |
| Version control | Git |

---

## Data plan (the bottleneck, start first)

- Choose about 12 tricky local items (coffee cup, compostable cutlery, food-soiled paper, greasy container, chip bag, and similar).
- Photograph about 30 examples of each, clean and contaminated, in varied lighting.
- Keep a **held-out test set** we never train on.
- Report accuracy on that test set honestly, including failures.
- Verify rules against the current Recycle BC and Metro Vancouver accepted-materials lists before hard-coding anything. **Not yet verified.**

---

## 24-hour timeline

| Hours | Goal |
|---|---|
| 0-2 | Lock scope, pick 12 items, pull and verify local rules, assign roles |
| 2-8 | Collect and label photos, split off test set |
| 8-14 | Fine-tune model, wire to rule table, output bin + reason |
| 14-18 | Hardware demo: two cameras, Pi, bin indicators, devnet payout |
| 18-22 | Dashboard, anti-abuse checks, seeded demo flow that never depends on live luck |
| 22-24 | Rehearse the 3-minute pitch out loud, twice |

## Team roles

| Role | Owner |
|---|---|
| Hardware (two cameras, Pi, indicators) | TBD |
| Data + model + rule table | TBD |
| Backend + payout + dashboard | TBD |
| Pitch + demo script | TBD |

---

## Awards we're targeting (HackCamp 2026)

We are a **beginner team**, so the Beginner stream applies.

| Award | Why we fit | What we must do |
|---|---|---|
| Overall Winner / Beginner Overall Winner | Automatic, no opt-in | Working demo, clear pitch |
| Best Problem-Solution Fit (beginner only) | Clear problem (local sorting rules + contamination) and a direct solution | Opt in. Write a problem statement and solution description in Devpost |
| Best Hardware | Two cameras + Raspberry Pi bin | Opt in. Show the physical bin working in the demo |
| Community Impact | Cleaner recycling and compost streams for a community | Opt in. Write a brief impact statement in Devpost |
| MLH: Best Use of Solana | Reward payouts on Solana | Opt in. Solana must be a real part of the flow. Confirm with MLH mentors that devnet is acceptable |
| Sponsor: Best Use of Databricks | Activity log and contamination analytics | Opt in. Use at least one Databricks product for real (Delta table + dashboard) |
| MLH: Best Use of Gemini API | Explanations and photo auto-labeling | Opt in. Gemini must do real work in the product, not a token call |
| MLH: Best Domain (GoDaddy Registry) | Only if our domain is eligible | See the domain note below |

**Not targeting:** Most Accessible Design and Best Design (both need a Figma file and design time we don't have). Revisit only if a teammate wants to own Figma.

### Domain note (important)
- cashcan.com is a **.com**, which is run by Verisign, not GoDaddy Registry. The award requires an "eligible GoDaddy Registry domain name", so cashcan.com is **likely not eligible**.
- GoDaddy Registry operates TLDs such as .co, .us, .biz, .club, .nyc, .design and .tv. A domain like **cashcan.co** would likely qualify.
- Availability of cashcan.co (or similar) is **not checked**, and the exact eligible list should be confirmed with MLH or the GoDaddy Registry table at the event.
- Decide before the hackathon: keep cashcan.com for branding and skip this award, or register an eligible domain too. Do not claim the award with an ineligible domain.

## Submission checklist (Devpost)

- [ ] Link to GitHub repository
- [ ] Recorded demo video, max 4 minutes (optional but highly recommended)
- [ ] Figma link (only if applying for a design award)
- [ ] Opt in to each award we want, and read each award's extra requirements
- [ ] Problem statement and solution description (Best Problem-Solution Fit)
- [ ] Brief impact statement (Community Impact)
- [ ] Hardware component shown (Best Hardware)
- [ ] Databricks product used, with a short explanation
- [ ] Gemini API usage, with a short explanation
- [ ] Solana integration, with a short explanation
- [ ] Domain eligibility confirmed (if opting in)

## Pitch notes

- **Opening line:** "It says compostable. In Vancouver, it still goes in the garbage."
- Show the bin catching a contaminated item live, then the payout changing.
- Show real held-out accuracy, including where the model fails.
- Say plainly: "We found no product doing local-rule plus contamination sorting, but our dataset is small."
- **Who funds the payouts:** the recycling/hauling company that picks up the bin's contents pays CashCan cash for the collected material. CashCan converts part of that revenue into SOL to fund the treasury wallet, which pays users per reward-eligible item. See `backend/README.md` for the devnet implementation of the payout leg.
- Be ready to explain how this differs from existing deposit-refund programs for drink containers.
- Have a one-sentence answer for "why facial recognition?" (for example: it ties each reward to one real person without carrying a card or phone) and for privacy: opt-in, embeddings only, deletable.

---

## Known risks and limits

- Small self-collected dataset: this is a prototype, not a solved problem.
- Classifier accuracy will drop on messy real-world items.
- Payout abuse is possible without strong rate limits and confidence thresholds.
- Crypto adds regulatory and credibility questions. We use devnet only.
- The public devnet faucet is unreliable for a live demo: Solana shut off its RPC auto-airdrop, and the web faucet explicitly tells AI agents/scripts not to use its form. We demo against a local `solana-test-validator` instead (unlimited SOL, no rate limit, no network dependency during judging) — see `backend/README.md` for both setups.
- Facial recognition handles biometric data, which carries privacy and legal obligations (consent, storage, deletion). We have not verified what applies in BC. Keep it opt-in, store embeddings only, and be ready to explain why a face is needed at all.
- Face matching can be fooled by a photo or screen without liveness detection, and accuracy varies across lighting and faces. Test on our own team and report real results.
- Local rules change. Rules in this project are as of build time and must be re-verified.

## Open questions

- [ ] Definition of the payout formula ("Classifier / 2")
- [x] Who funds real payouts in a real deployment — the recycling/hauling company's payment for collected material, converted to SOL (see backend/README.md)
- [ ] Domain: keep cashcan.com (likely ineligible for the GoDaddy Registry award) or also register an eligible TLD such as .co. Check trademark clearance for the name either way
- [ ] Which face recognition library, and which camera does the face match (shared with the front item camera, or a third camera)
- [ ] Camera placement and how the two views are combined (top = entry angle, front = side profile)
- [ ] Which items are reward-eligible and how much each pays
- [ ] Final list of 12 items and their verified local rules

---

## Credits

Team: TBD
