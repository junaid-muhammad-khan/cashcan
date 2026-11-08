"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth0 } from "@auth0/auth0-react";
import { useCallback, useEffect, useRef, useState } from "react";
import AuthShell from "@/components/AuthShell";
import { Check, LogoMark } from "@/components/icons";
import { checkPose, enroll, FaceApiError, getMe, matchFrame, userIdFromSub, type MatchResult, type Me } from "@/lib/faceApi";
import { ServicePaused } from "@/components/ServicePaused";
import { isDbPaused } from "@/lib/errors";
import { useCamera } from "./useCamera";

type Step = "loading" | "paused" | "already" | "consent" | "camera" | "scan" | "saving" | "duplicate" | "test" | "done";

// The face API accepts 1-3 enrollment frames (face_api/app/config.py); three angles give the best recall.
// Each photo is taken only once the API sees the head really turned that way (POST /pose), so "left" is never a front photo.
const POSES = [
  { label: "Straight", want: "front", cue: "Look straight at the camera", cls: "" },
  { label: "Left", want: "left", cue: "Turn your head a little to your left", cls: "nudge-l" },
  { label: "Right", want: "right", cue: "Now a little to your right", cls: "nudge-r" },
] as const;
const POLL_MS = 350;
const POSE_TIMEOUT_MS = 30000;
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const AUDIENCE = process.env.NEXT_PUBLIC_AUTH0_AUDIENCE;

const STEPPER = ["Consent", "Scan", "Test", "Done"];
const stepIndex = (s: Step) => (s === "consent" || s === "loading" || s === "already" || s === "paused" ? 0 : s === "test" ? 2 : s === "done" ? 3 : 1);

export default function EnrollFlow() {
  const { user, getAccessTokenSilently } = useAuth0();
  const router = useRouter();
  const cam = useCamera();
  const [step, setStep] = useState<Step>("loading");
  const [token, setToken] = useState<string | undefined>();
  const [me, setMe] = useState<Me | null>(null);
  const [consent, setConsent] = useState(false);
  const [wallet, setWallet] = useState("");
  const [errs, setErrs] = useState<{ consent?: string }>({});
  const [error, setError] = useState<string | null>(null);
  const [problems, setProblems] = useState<string[]>([]);
  const [captured, setCaptured] = useState(0);
  const [flash, setFlash] = useState(false);
  const [liveHint, setLiveHint] = useState("");
  const [dupFrames, setDupFrames] = useState<Blob[] | null>(null);  // the photos that matched an existing account, kept so they can be re-sent with replace
  const [test, setTest] = useState<{ busy: boolean; score?: number; ok?: boolean; message?: string }>({ busy: false });
  const runId = useRef(0);

  // Who is this, and are they already enrolled? Works without Auth0 on the API too (local dev).
  useEffect(() => {
    let cancelled = false;
    (async () => {
      let t: string | undefined;
      try {
        if (AUDIENCE) t = await getAccessTokenSilently({ authorizationParams: { audience: AUDIENCE } });
      } catch { /* no API token: fall back to local mode, the API will say if it needs one */ }
      let profile: Me | null = null;
      let paused = false;
      if (t) {
        try { profile = await getMe(t); } catch (e) { if (isDbPaused(e)) paused = true; /* otherwise: accounts not configured on the API */ }
      }
      if (cancelled) return;
      if (paused) { setStep("paused"); return; }
      setToken(t);
      setMe(profile);
      if (profile?.sol_wallet) setWallet(profile.sol_wallet);
      if (profile?.face_enrolled && profile.sol_wallet) {
        // Already set up (e.g. an existing account logging in again): nothing to do here, go straight to the dashboard.
        router.replace("/dashboard");
        return;
      }
      setStep(profile?.face_enrolled ? "already" : "consent");
    })();
    return () => { cancelled = true; };
  }, [getAccessTokenSilently, router]);

  const needsWallet = !me?.sol_wallet;

  async function onConsentContinue() {
    if (!consent) { setErrs({ consent: "Tick the box to continue. Face match is required to use CashCan." }); return; }
    setErrs({});
    setError(null);
    setStep("camera");
    await cam.start();
  }

  // A REAL check, not a replay of what was just saved: the person turns back to the camera, then three fresh pictures taken over about a
  // second are matched against the saved face, the way a bin does it. At least two must match this account (and nobody else).
  const verify = useCallback(async (id: number) => {
    setStep("test");
    setTest({ busy: true });
    setLiveHint("Now look straight at the camera for a quick check.");
    let streak = 0;
    const t0 = Date.now();
    while (Date.now() - t0 < 20000 && streak < 2) {            // wait until they are facing the camera again (the last photo was a turned head)
      if (runId.current !== id) return;
      const f = await cam.capture();
      if (f) {
        try {
          const r = await checkPose(f);
          if (r.found && r.pose === "front") { streak++; setLiveHint("Hold still…"); }
          else { streak = 0; setLiveHint(r.hint || "Now look straight at the camera for a quick check."); }
        } catch { /* try again */ }
      }
      await sleep(POLL_MS);
    }
    const results: MatchResult[] = [];
    for (let i = 0; i < 3; i++) {
      if (runId.current !== id) return;
      await sleep(i === 0 ? 400 : 350);
      const f = await cam.capture();
      try { if (f) results.push(await matchFrame(f)); } catch (e) { results.push({ matched: false, message: (e as Error).message }); }
    }
    if (runId.current !== id) return;
    const mine = (r: MatchResult) => !!r.matched && (!me?.user_id || r.user_id === me.user_id);
    const wrong = results.filter((r) => r.matched && me?.user_id && r.user_id !== me.user_id).length;
    const ok = results.filter(mine).length >= 2 && wrong === 0;
    // The numbers stay in the log, not on screen; 0.45 is the match threshold (face_api MATCH_THRESHOLD).
    console.info("[cashcan] face verification", { ok, frames: results.map((r) => ({ matched: mine(r), similarity: r.score ?? null, reason: r.reason ?? null })), threshold: 0.45 });
    setLiveHint("");
    setTest({
      busy: false, ok,
      message: ok ? undefined : "We couldn't match fresh pictures of you to your saved face. Look straight at the camera in good light and verify again.",
    });
  }, [cam, me]);

  async function verifyAgain() {
    const id = ++runId.current;
    await verify(id);
  }

  // Send the photos. replace=true deletes the old account that holds this same face (the person chose that in the "duplicate" step).
  const save = useCallback(async (frames: Blob[], replace: boolean, id: number) => {
    try {
      await enroll(frames, { token, userId: me?.user_id ?? userIdFromSub(user?.sub ?? "user"), wallet: wallet.trim(), poses: POSES.map((p) => p.want), replace });
    } catch (e) {
      const err = e as FaceApiError;
      if (runId.current !== id) return;
      if (err.status === 409 && /already enrolled/i.test(err.message)) { cam.stop(); try { sessionStorage.removeItem("cashcan.profile.v1"); } catch { /* ignore */ } router.replace("/dashboard"); return; }
      if (err.code === "face_already_registered") { cam.stop(); setDupFrames(frames); setStep("duplicate"); return; }
      setProblems(err.problems.map(friendlyProblem));
      setError(err.status === 422 ? "Some pictures weren't clear enough to save. Check the tips below and scan again." : err.message);
      setStep("camera");
      if (cam.state !== "on") cam.start();
      return;
    }
    if (runId.current !== id) return;
    setDupFrames(null);
    try { sessionStorage.removeItem("cashcan.profile.v1"); } catch { /* ignore */ }  // force a fresh profile (face_enrolled is now true)
    await verify(id);
  }, [cam, me, router, token, user, verify, wallet]);

  async function replaceOldAccount() {
    if (!dupFrames) return;
    const id = ++runId.current;
    setError(null);
    setStep("saving");
    await save(dupFrames, true, id);
  }

  const runScan = useCallback(async () => {
    const id = ++runId.current;
    setProblems([]);
    setError(null);
    setCaptured(0);
    setStep("scan");
    const frames: Blob[] = [];
    for (let i = 0; i < POSES.length; i++) {
      // Wait until the API sees this direction in two consecutive looks, then keep that frame.
      let streak = 0, kept: Blob | null = null;
      const t0 = Date.now();
      setLiveHint("");
      while (!kept && Date.now() - t0 < POSE_TIMEOUT_MS) {
        if (runId.current !== id) return; // restarted or left
        const f = await cam.capture();
        if (!f) { await sleep(POLL_MS); continue; }
        try {
          const r = await checkPose(f);
          if (runId.current !== id) return;
          if (r.found && r.pose === POSES[i].want) {
            streak++;
            setLiveHint("Hold still…");
            if (streak >= 2) kept = f;
          } else {
            streak = 0;
            setLiveHint(r.found ? (r.hint || POSES[i].cue) : (r.hint || "Move into the oval so we can see your face."));
          }
        } catch (e) {
          setError((e as Error).message);
          setStep("camera");
          return;
        }
        if (!kept) await sleep(POLL_MS);
      }
      if (!kept) { setError(`We didn't see your head ${POSES[i].want === "front" ? "facing the camera" : "turned to your " + POSES[i].want}. Start the scan again.`); setStep("camera"); return; }
      frames.push(kept);
      setFlash(true);
      setTimeout(() => setFlash(false), 180);
      setCaptured(i + 1);
    }
    setLiveHint("");
    setStep("saving");
    await save(frames, false, id);
  }, [cam, save]);

  function restart() {
    runId.current++;
    setDupFrames(null);
    setError(null);
    setCaptured(0);
    setTest({ busy: false });
    setStep("camera");
    if (cam.state !== "on") cam.start();
  }

  function finish() {
    runId.current++;
    cam.stop();
    setStep("done");
  }

  const si = stepIndex(step);
  const showCamera = step === "camera" || step === "scan" || step === "saving" || step === "test";
  const pose = POSES[Math.min(captured, POSES.length - 1)];
  const ring = 660 - 660 * (captured / POSES.length);

  const journey = [
    { title: "Create your account", sub: "Done", done: true },
    { title: "Link a crypto wallet", sub: needsWallet ? "Add it in your profile" : "Linked", done: !needsWallet },
    { title: "Set up face match", sub: step === "done" || step === "already" ? "Ready at any bin" : "About a minute", done: step === "done" || step === "already" },
  ];

  return (
    <AuthShell
      heading="Your face is your bin card."
      body="Step up to any CashCan bin and it knows who to credit. No phone, no card, no app."
      wide
      aside={
        <ol className="journey" aria-label="Your setup progress">
          {journey.map((j, i) => (
            <li key={j.title} className={j.done ? "done" : undefined}>
              <span className="mark" aria-hidden="true">{j.done ? "✓" : i + 1}</span>
              <span><b>{j.title}<span className="sr-only">{j.done ? " (done)" : " (to do)"}</span></b><small>{j.sub}</small></span>
            </li>
          ))}
        </ol>
      }
    >
      <div className="en-stepper" aria-label={`Step ${si + 1} of 4`}>
        {STEPPER.map((l, i) => (
          <div key={l} className={i <= si ? "on" : undefined} aria-current={i === si ? "step" : undefined}><span /><small>{l}</small></div>
        ))}
      </div>

      {step === "loading" && <p className="sub">Getting your account ready…</p>}
      {step === "paused" && <ServicePaused onRetry={() => window.location.reload()} />}

      {step === "already" && (
        <div className="success-panel en-fade" role="status">
          <span className="en-done-mark"><LogoMark size={56} /><span className="en-done-check"><Check size={13} color="#fff" strokeWidth={3.2} /></span></span>
          <h1>Face match is already set up</h1>
          <p className="sub">Your face template is saved, so any CashCan bin can recognise you. To redo it, delete it from your profile first.</p>
          <div className="cta-row" style={{ marginTop: 22 }}>
            <Link href="/dashboard" className="btn btn-primary">Go to your dashboard</Link>
            <Link href="/account" className="btn btn-ghost">Profile</Link>
          </div>
        </div>
      )}

      {step === "duplicate" && (
        <div className="success-panel en-fade" role="alert">
          <h1>This face is already registered</h1>
          <p className="sub">Your face matches another CashCan account. One face can belong to only one account.</p>
          <p className="sub" style={{ marginTop: 10 }}>
            If that old account is yours, you can <b>delete it and use this account as your main one</b>. The old account&apos;s saved face data and profile
            will be permanently removed, and rewards will go to the wallet on this account from now on.
          </p>
          {error && <div className="alert" style={{ marginTop: 14 }}>{error}</div>}
          <div className="cta-row" style={{ marginTop: 22 }}>
            <button type="button" className="btn btn-primary" onClick={replaceOldAccount}>Delete the old account and use this one</button>
            <button type="button" className="btn btn-ghost" onClick={restart}>Scan again</button>
          </div>
          <p className="sub" style={{ marginTop: 14, fontSize: 13 }}>Not your face? Don&apos;t delete anything; scan again or contact the CashCan team.</p>
        </div>
      )}

      {step === "consent" && (
        <div className="en-fade">
          <h1>Set up face match</h1>
          <p className="sub">Takes about a minute. Face match is required: the bin uses it to know who to pay.</p>
          <div className="en-facts">
            {[
              ["512", "Numbers, not photos", "Your face becomes a 512-number template. Camera pictures are thrown away."],
              ["3", "Three quick angles", "Straight, then a little left and right, so any bin can find you."],
              ["✕", "Yours to delete", "Remove the template and it stops working at every bin at once."],
            ].map(([b, t, d]) => (
              <div key={t} className="en-fact"><span>{b}</span><b>{t}</b><small>{d}</small></div>
            ))}
          </div>

          <label className="check check-card" style={{ marginTop: 16, borderColor: errs.consent ? "var(--danger)" : undefined }}>
            <input type="checkbox" checked={consent} onChange={(e) => { setConsent(e.target.checked); setErrs((x) => ({ ...x, consent: undefined })); }} />
            <span>I agree to let CashCan create a face template from my camera to recognize me at bins, and I can delete it any time.</span>
          </label>
          {errs.consent && <p className="en-err" role="alert">{errs.consent}</p>}
          {error && <div className="alert" role="alert" style={{ marginTop: 16 }}>{error}</div>}

          <div className="cta-row" style={{ marginTop: 24 }}>
            <button type="button" className="btn btn-primary" onClick={onConsentContinue}>Continue</button>
          </div>
        </div>
      )}

      {showCamera && (
        <div className="en-fade">
          <h1 className="en-title">
            {step === "camera" ? "Check your camera" : step === "scan" ? (captured >= POSES.length ? "Got it" : pose.cue)
              : step === "saving" ? "Saving your templates…" : test.busy ? "Checking it works…" : test.ok ? "It recognises you" : "We couldn't verify you yet"}
          </h1>
          <p className="sub">
            {step === "camera" ? "Fit your face inside the oval, in even light, about an arm's length away. Glasses are fine; hats and masks are not."
              : step === "scan" ? "Hold each position. We take the picture automatically."
              : step === "saving" ? "Turning your pictures into templates. The pictures themselves are not kept."
              : test.busy ? (liveHint || "Look straight at the camera for a quick check.")
              : test.ok ? "We matched fresh pictures of you against your saved face, the same way a bin will."
              : test.message}
          </p>

          <div className={`en-cam${flash ? " flash" : ""}`}>
            <video ref={cam.videoRef} playsInline muted aria-label="Your camera preview" />
            <svg viewBox="0 0 400 300" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
              <defs><mask id="en-oval"><rect width="400" height="300" fill="white" /><ellipse cx="200" cy="146" rx="88" ry="112" fill="black" /></mask></defs>
              <rect width="400" height="300" fill="rgba(15,31,23,.45)" mask="url(#en-oval)" />
              <ellipse cx="200" cy="146" rx="88" ry="112" fill="none" stroke="rgba(255,255,255,.35)" strokeWidth="3" />
              <ellipse className="en-ring" cx="200" cy="146" rx="88" ry="112" fill="none" stroke="#5FD79A" strokeWidth="5" strokeLinecap="round"
                strokeDasharray="660" strokeDashoffset={ring} transform="rotate(-90 200 146)" />
            </svg>
            {cam.state !== "on" && (
              <div className="en-cam-msg">
                {cam.state === "starting" && "Starting your camera…"}
                {cam.state === "denied" && <>Camera access is blocked. Allow it in your browser&apos;s address bar, then <button type="button" onClick={() => cam.start()}>try again</button>.</>}
                {cam.state === "unavailable" && "No camera found. Face match needs a camera on this device, or you can enroll at a bin."}
                {cam.state === "idle" && <button type="button" onClick={() => cam.start()}>Turn on camera</button>}
              </div>
            )}
            {step === "scan" && captured < POSES.length && (
              <div className="en-cue"><span className={pose.cls} aria-hidden="true">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"
                  style={{ transform: pose.cls === "nudge-l" ? "rotate(180deg)" : pose.cls ? "none" : "rotate(90deg)" }}><path d="M5 12h14M13 6l6 6-6 6" /></svg>
              </span>{liveHint || (pose.label === "Straight" ? "Look straight ahead" : pose.cue)}</div>
            )}
            {step === "test" && test.busy && liveHint && <div className="en-cue">{liveHint}</div>}
            <span className="en-count" aria-live="polite">{captured} of {POSES.length}</span>
          </div>

          <div className="en-frames">
            {POSES.map((p, i) => {
              const done = i < captured, active = step === "scan" && i === captured;
              return (
                <div key={p.label} className={done ? "done" : active ? "active" : undefined}>
                  <span>{done ? "✓" : i + 1}</span><small>{p.label}</small>
                </div>
              );
            })}
          </div>

          {error && <div className="alert" role="alert" style={{ marginTop: 14 }}>{error}</div>}
          {problems.length > 0 && <ul className="en-problems">{problems.map((p) => <li key={p}>{p}</li>)}</ul>}

          {step === "test" && !test.busy && test.ok && (
            <p className="en-score"><b>Go ahead, grab your cashback.</b></p>
          )}

          <div className="cta-row" style={{ marginTop: 20 }}>
            {step === "camera" && <button type="button" className="btn btn-primary" disabled={cam.state !== "on"} onClick={runScan}>Start scan</button>}
            {step === "scan" && <button type="button" className="btn btn-ghost" onClick={restart}>Start over</button>}
            {step === "test" && !test.busy && (
              <>
                <button type="button" className={`btn ${test.ok ? "btn-primary" : "btn-ghost"}`} onClick={finish}>{test.ok ? "Finish setup" : "Finish anyway"}</button>
                {!test.ok && <button type="button" className="btn btn-primary" onClick={verifyAgain}>Verify again</button>}
                <button type="button" className="btn btn-ghost" onClick={restart}>Scan again</button>
              </>
            )}
            {step === "camera" && <button type="button" className="btn btn-ghost" onClick={() => { cam.stop(); setStep("consent"); }}>Back</button>}
          </div>
        </div>
      )}

      {step === "done" && (
        <div className="success-panel en-fade" role="status">
          <span className="en-done-mark"><LogoMark size={56} /><span className="en-done-check"><Check size={13} color="#fff" strokeWidth={3.2} /></span></span>
          <h1>Face match is ready</h1>
          <p className="sub">
            Next time you&apos;re at a CashCan bin, look at the front camera. It asks you to turn your head once so it knows you&apos;re really there,
            then credits what you sort for the next two minutes.
          </p>
          <ul className="en-done-list">
            <li><Check />Templates saved, no photos kept</li>
            <li><Check />Rewards go to {wallet ? `${wallet.slice(0, 4)}…${wallet.slice(-4)}` : "your wallet"}</li>
            <li><Check />Delete or redo it any time</li>
          </ul>
          {needsWallet && (
            <div className="alert" role="alert" style={{ marginTop: 16 }}>
              Add a Solana wallet in your profile first. That&apos;s where CashCan sends your SOL rewards.
            </div>
          )}
          <div className="cta-row" style={{ marginTop: 24 }}>
            {needsWallet ? (
              <Link href="/account" className="btn btn-primary">Add wallet in profile</Link>
            ) : (
              <Link href="/dashboard?welcome=1" className="btn btn-primary">Go to your dashboard</Link>
            )}
          </div>
        </div>
      )}
    </AuthShell>
  );
}

// Turn the API's quality messages ("frame 2: face too small: 62px < 80px") into advice.
function friendlyProblem(p: string): string {
  const s = p.toLowerCase();
  const frame = p.match(/frame (\d+)/i)?.[1];
  const which = frame ? `${POSES[Number(frame) - 1]?.label ?? `Picture ${frame}`}: ` : "";
  if (s.includes("small")) return `${which}your face was too far away. Move a little closer.`;
  if (s.includes("blur") || s.includes("sharp")) return `${which}the picture was blurry. Hold still and add some light.`;
  if (s.includes("no face")) return `${which}no face was found. Keep your face inside the oval.`;
  if (s.includes("faces") || s.includes("more than one")) return `${which}more than one face was in view. Make sure it's just you.`;
  return `${which}${p.replace(/^frame \d+:\s*/i, "")}`;
}
