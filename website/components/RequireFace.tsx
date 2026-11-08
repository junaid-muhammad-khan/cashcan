"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import type { HeldRelease, Me } from "@/lib/faceApi";
import { DB_PAUSED } from "@/lib/errors";
import { useProfile } from "@/lib/useProfile";
import PausedScreen from "./ServicePaused";

// Face match is mandatory: a signed-in user without an enrolled face and a wallet is sent to /enroll.
// If the profile can't be loaded we do NOT let the page through; we show a retry instead.
// NEXT_PUBLIC_REQUIRE_FACE=0 turns the gate off for local development without a face service.
const GATE_OFF = process.env.NEXT_PUBLIC_REQUIRE_FACE === "0";

type Props = { me: Me | null; setWallet: (w: string) => Promise<HeldRelease>; getToken: () => Promise<string> };

export default function RequireFace({ children }: { children: (p: Props) => React.ReactNode }) {
  const router = useRouter();
  const { state, reload, setWallet, getToken } = useProfile();
  const missing = state.status === "ready" && !(state.me.face_enrolled && state.me.sol_wallet);

  useEffect(() => {
    if (!GATE_OFF && missing) router.replace("/enroll");
  }, [missing, router]);

  if (GATE_OFF) return <>{children({ me: state.status === "ready" ? state.me : null, setWallet, getToken })}</>;
  if (state.status === "loading" || missing) return <p style={{ padding: 48 }}>Checking your face match…</p>;
  if (state.status === "error" && state.code === DB_PAUSED) return <PausedScreen current="dashboard" onRetry={reload} message={state.message} />;
  if (state.status === "error") {
    return (
      <div style={{ padding: 48, maxWidth: 560 }}>
        <h1 style={{ fontSize: 28 }}>We couldn&apos;t check your face match</h1>
        <p className="sub" style={{ margin: "12px 0 20px" }}>{state.message}</p>
        <button type="button" className="btn btn-primary" onClick={reload}>Try again</button>
      </div>
    );
  }
  return <>{children({ me: state.me, setWallet, getToken })}</>;
}
