"use client";

import { useAuth0 } from "@auth0/auth0-react";
import { useCallback, useEffect, useState } from "react";
import { getMe, saveWallet, type Me } from "./faceApi";

const AUDIENCE = process.env.NEXT_PUBLIC_AUTH0_AUDIENCE;
const need = (v: string | undefined, what: string): string => { if (!v) throw new Error(what); return v; };

export type ProfileState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; me: Me };

/** The signed-in user's profile from the face API (wallet, face enrolled), via an Auth0 access token for that API. */
export function useProfile() {
  const { getAccessTokenSilently } = useAuth0();
  const [state, setState] = useState<ProfileState>({ status: "loading" });
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setState({ status: "loading" });
      try {
        const audience = need(AUDIENCE, "The face service is not configured (NEXT_PUBLIC_AUTH0_AUDIENCE is missing).");
        const token = need(await getAccessTokenSilently({ authorizationParams: { audience } }), "Could not get a login token for the face service.");
        const me = await getMe(token);
        if (!cancelled) setState({ status: "ready", me });
      } catch (e) {
        if (!cancelled) setState({ status: "error", message: (e as Error).message || "We couldn't load your profile." });
      }
    })();
    return () => { cancelled = true; };
  }, [getAccessTokenSilently, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);

  const setWallet = useCallback(async (wallet: string) => {
    const audience = need(AUDIENCE, "The face service is not configured.");
    const token = need(await getAccessTokenSilently({ authorizationParams: { audience } }), "Could not get a login token for the face service.");
    const updated = await saveWallet(token, wallet);
    setState((s) => (s.status === "ready" ? { status: "ready", me: { ...s.me, ...updated } } : s));
  }, [getAccessTokenSilently]);

  return { state, reload, setWallet };
}
