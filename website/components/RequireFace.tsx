"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import type { Me } from "@/lib/faceApi";
import { useProfile } from "@/lib/useProfile";

// Face match is mandatory: a signed-in user without an enrolled face and a wallet is sent to /enroll.
// If the profile can't be loaded we do NOT let the page through; we show a retry instead.
// NEXT_PUBLIC_REQUIRE_FACE=0 turns the gate off for local development without a face service.
const GATE_OFF = process.env.NEXT_PUBLIC_REQUIRE_FACE === "0";

export default function RequireFace({ children }: { children: (p: { me: Me | null; setWallet: (w: string) => Promise<void> }) => React.ReactNode }) {
  const router = useRouter();
  const { state, reload, setWallet } = useProfile();
  const missing = state.status === "ready" && !(state.me.face_enrolled && state.me.sol_wallet);

  useEffect(() => {
    if (!GATE_OFF && missing) router.replace("/enroll");
  }, [missing, router]);

  if (GATE_OFF) return <>{children({ me: state.status === "ready" ? state.me : null, setWallet })}</>;
  if (state.status === "loading" || missing) return <p style={{ padding: 48 }}>Checking your face match…</p>;
  if (state.status === "error") {
    return (
      <div style={{ padding: 48, maxWidth: 560 }}>
        <h1 style={{ fontSize: 28 }}>We couldn&apos;t check your face match</h1>
        <p className="sub" style={{ margin: "12px 0 20px" }}>{state.message}</p>
        <button type="button" className="btn btn-primary" onClick={reload}>Try again</button>
      </div>
    );
  }
  return <>{children({ me: state.me, setWallet })}</>;
}
