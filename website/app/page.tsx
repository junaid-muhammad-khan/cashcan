import Link from "next/link";
import HomeMotion from "@/components/HomeMotion";
import LiveFeed from "@/components/LiveFeed";
import SiteNav from "@/components/SiteNav";
import { Check, Coin, Drop, Person, Pin } from "@/components/icons";

const STEPS = [
  { title: "Step up, get recognised", body: "An opt-in face match identifies you at the bin and links the drop to your Solana wallet. Only face embeddings are stored, never photos." },
  { title: "Two cameras look at the item", body: "A top camera and a front camera capture the item from two angles, so a detection is more reliable and much harder to fool." },
  { title: "Sorted by your city, not by material", body: "The classifier picks Organics, Cans or Waste, then the local rule table says where it really goes and shows a plain-language reason." },
  { title: "Anti-abuse gates", body: "Confidence threshold, camera agreement, a per-user cooldown and a liveness check all have to pass before anything is paid." },
  { title: "Paid and logged", body: "Reward-eligible items pay out in SOL on devnet. Every decision, paid or rejected, lands in Databricks for the dashboard." },
];

const GATES = [
  ["Classifier confidence", "0.93 ≥ 0.75"],
  ["Top + front cams agree", "can = can"],
  ["Cooldown since last drop", "41 s ≥ 30 s"],
  ["Liveness check", "passed"],
];

const PRIVACY = [
  ["Opt-in only", "Nobody is enrolled without a consent screen."],
  ["Embeddings, not photos", "The bin stores a numeric face template. Raw images are never kept."],
  ["Delete on request", "Remove your face data and account at any time."],
];

export default function Home() {
  return (
    <HomeMotion>
      {/* ===== HERO ===== */}
      <header className="hero" id="top">
        <div aria-hidden="true" className="blob" style={{ width: 520, height: 520, background: "#9BE3BC", left: -120, top: 60 }} />
        <div aria-hidden="true" className="blob" style={{ width: 460, height: 460, background: "#F3D58A", right: -80, top: 220 }} />
        <div aria-hidden="true" className="blob" style={{ width: 380, height: 380, background: "#B9D7F0", left: "40%", top: 520 }} />
        <div aria-hidden="true" className="dots" />

        <SiteNav />

        <div className="hero-grid container">
          <div>
            <h1 data-intro>It says compostable.<br /><em>In Vancouver, it still goes in the garbage.</em></h1>
            <p className="lede" data-intro>
              CashCan tells you the truth about what&apos;s recyclable in your city, catches contamination
              before it ruins the batch, and pays you real SOL the moment you get it right.
            </p>
            <div className="cta-row" data-intro>
              <Link href="/signup" className="btn btn-primary">Create free account</Link>
              <a href="#how" className="btn btn-ghost">See how it works →</a>
            </div>
            <div className="checks" data-intro>
              <span><Check />Local-rule aware</span>
              <span><Check />Contamination aware</span>
              <span><Check />Opt-in face match</span>
            </div>
          </div>

          <div className="mock-wrap">
            <div className="mock">
              <div className="mock-bar"><i /><i /><i /><small>cashcan · bin #04</small><b>Preview</b></div>
              <LiveFeed />
            </div>
            <div className="float float-payout">
              <span style={{ width: 36, height: 36, borderRadius: "50%", background: "#2BB673", display: "flex", alignItems: "center", justifyContent: "center" }}>
                <Check size={18} color="#0F1F17" strokeWidth={3} />
              </span>
              <span><b>Payout sent</b><small>+0.004 SOL · aluminum can</small></span>
            </div>
            <div className="float float-contam">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: 12, fontWeight: 600, color: "#8A5A00" }}>Contaminated</span>
                <span style={{ fontSize: 11, color: "#5C6B62" }}>front cam</span>
              </div>
              <div style={{ fontSize: 14, fontWeight: 600, marginTop: 6 }}>Greasy plastic tray</div>
              <div className="meter"><i /></div>
              <div style={{ fontSize: 12, color: "#5C6B62", marginTop: 6 }}>Reward reduced to 25%</div>
            </div>
            <div className="float float-face"><Person />Face matched · Maya R.</div>
          </div>
        </div>
      </header>

      <main>
        {/* ===== STRIP ===== */}
        <section aria-label="Built with" className="strip">
          <div className="container" data-reveal>
            <small>Built on</small>
            <span>Raspberry Pi + 2 cameras</span><span className="sep" aria-hidden="true">/</span>
            <span>MobileNetV2 classifier</span><span className="sep" aria-hidden="true">/</span>
            <span>Solana devnet payouts</span><span className="sep" aria-hidden="true">/</span>
            <span>Databricks activity log</span>
          </div>
        </section>

        {/* ===== PROBLEM ===== */}
        <section className="section" id="rules">
          <div className="container">
            <div style={{ maxWidth: 760 }} data-reveal>
              <div className="eyebrow">The problem</div>
              <h2>One greasy container can ruin a whole batch of recycling.</h2>
              <p className="section-lede">
                Sorting rules are local and confusing, smart bins classify material instead of what your city accepts,
                and there is little reason for anyone to get it right. CashCan fixes all three at the bin.
              </p>
            </div>
            <div className="three">
              <article className="card" data-reveal>
                <div className="icon-tile" style={{ background: "#E3F5EB" }}><Pin /></div>
                <h3>Your city&apos;s rules, not a material label</h3>
                <p>Every decision is looked up against a local rule table, so the bin says where an item really goes in Metro Vancouver, and why.</p>
              </article>
              <article className="card" data-reveal>
                <div className="icon-tile" style={{ background: "#FBF1D8" }}><Drop /></div>
                <h3>Catches contamination</h3>
                <p>A top camera and a front camera must agree. Food-soiled or greasy items are flagged and earn a reduced reward instead of slipping through.</p>
              </article>
              <article className="card" data-reveal>
                <div className="icon-tile" style={{ background: "#E4EEF8" }}><Coin /></div>
                <h3>A reason to get it right</h3>
                <p>Reward-eligible items pay out instantly to your Solana wallet. The hauler that buys the sorted material funds the rewards.</p>
              </article>
            </div>
          </div>
        </section>

        {/* ===== STORY ===== */}
        <section className="section story" id="how">
          <div className="container">
            <div style={{ maxWidth: 720 }} data-reveal>
              <div className="eyebrow">How an item flows through CashCan</div>
              <h2>Five seconds from drop to payout.</h2>
            </div>
            <div className="story-grid">
              <div className="story-visual" aria-hidden="true">
                <div className="grid-bg" />
                <div className="story-progress-label" data-step-label>Step 1 of 5</div>
                <div className="story-progress"><i /></div>

                <div className="scene center">
                  <div className="face-ring">
                    <Person size={90} color="#E6EEE9" strokeWidth={1.4} />
                    <div className="scan-line" />
                  </div>
                  <div className="tag-light">Matched · liveness passed</div>
                </div>
                <div className="scene">
                  <div className="cams">
                    <div className="cam"><small>TOP CAM</small><div style={{ width: 70, height: 70, borderRadius: "50%", border: "6px solid #9FB3A8" }} /><div className="box" style={{ inset: "40px 50px" }} /></div>
                    <div className="cam"><small>FRONT CAM</small><div style={{ width: 54, height: 96, borderRadius: 10, border: "6px solid #9FB3A8" }} /><div className="box" style={{ inset: "34px 60px" }} /></div>
                  </div>
                  <div style={{ textAlign: "center", fontSize: 14, color: "#CFE0D6" }}>Both views agree: <strong style={{ color: "#fff" }}>aluminum can</strong></div>
                </div>
                <div className="scene">
                  <div className="rule-row on"><span>Cans · Return-It</span><span>✓ this one</span></div>
                  <div className="rule-row"><span>Organics</span><span>—</span></div>
                  <div className="rule-row"><span>Waste</span><span>—</span></div>
                  <div style={{ fontSize: 13, color: "#8FB5A0", marginTop: 6 }}>&ldquo;Deposit containers go to Cans. Rinse first for the full reward.&rdquo;</div>
                </div>
                <div className="scene">
                  {GATES.map(([label, val]) => (
                    <div className="gate" key={label}>
                      <span className="tick"><Check size={14} color="#0F1F17" strokeWidth={3} /></span>
                      <span>{label}</span>
                      <small>{val}</small>
                    </div>
                  ))}
                </div>
                <div className="scene center">
                  <div className="payout-big">+0.004</div>
                  <div style={{ fontSize: 16, color: "#CFE0D6" }}>SOL sent to your wallet · devnet</div>
                  <div className="tag-light" style={{ fontSize: 13 }}><span className="live-dot" />Logged to Databricks</div>
                </div>
              </div>

              <ol className="steps">
                {STEPS.map((s, i) => (
                  <li className={`step${i === 0 ? " active" : ""}`} key={s.title}>
                    <div className="num">0{i + 1}</div>
                    <h3>{s.title}</h3>
                    <p>{s.body}</p>
                  </li>
                ))}
              </ol>
            </div>
          </div>
        </section>

        {/* ===== NUMBERS ===== */}
        <section className="section">
          <div className="container nums">
            {[
              [3, "", "bin openings: Organics, Cans and Waste"],
              [2, "", "cameras that must agree before a payout"],
              [75, "%", "minimum classifier confidence to pay"],
              [30, "s", "cooldown per user, against reward farming"],
            ].map(([n, suffix, label]) => (
              <div className="num-card" key={String(label)} data-reveal>
                <strong data-count={n} data-suffix={suffix}>{`${n}${suffix}`}</strong>
                <p>{label}</p>
              </div>
            ))}
          </div>
        </section>

        {/* ===== PRIVACY ===== */}
        <section className="section" id="privacy" style={{ paddingTop: 0 }}>
          <div className="container privacy">
            <div data-slide-left>
              <div className="eyebrow">Why a face?</div>
              <h2>It ties each reward to one real person, without a card or a phone.</h2>
              <p className="section-lede">Face match is opt-in. The bin checks liveness so a photo on a screen can&apos;t collect your rewards.</p>
            </div>
            <ul className="priv-list">
              {PRIVACY.map(([title, body]) => (
                <li key={title} data-pop>
                  <span className="tick"><Check size={14} color="#fff" strokeWidth={3} /></span>
                  <span><b>{title}</b><small>{body}</small></span>
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* ===== CTA ===== */}
        <section className="section" style={{ paddingTop: 0 }}>
          <div className="container cta" data-reveal>
            <div aria-hidden="true" className="blob" style={{ width: 420, height: 420, background: "#2BB673", opacity: 0.35, left: -100, top: -120 }} />
            <div aria-hidden="true" className="blob" style={{ width: 380, height: 380, background: "#E3B23C", opacity: 0.25, right: -80, bottom: -160 }} />
            <h2>Put a CashCan where people throw things away.</h2>
            <p>Campuses, offices, transit stations and events. Create an account, link your wallet, and start earning at the next bin.</p>
            <div className="cta-row">
              <Link href="/signup" className="btn btn-glow">Create free account</Link>
              <a href="#how" className="btn btn-outline-night">Read how it works</a>
            </div>
          </div>
        </section>
      </main>

      <footer className="footer">
        <div className="container">
          <span><strong style={{ fontFamily: "var(--font-display)", color: "#0F1F17" }}>cashcan</strong> · a HackCamp 2026 prototype. Payouts use Solana devnet test tokens only.</span>
          <nav aria-label="Footer"><a href="#privacy">Privacy</a><a href="#how">How it works</a><Link href="/login">Log in</Link></nav>
        </div>
      </footer>
    </HomeMotion>
  );
}
