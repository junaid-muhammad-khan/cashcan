"use client";

import { useAuth0 } from "@auth0/auth0-react";
import { useCallback, useEffect, useState } from "react";
import { getMe, saveWallet, type Me } from "./faceApi";

const AUDIENCE = process.env.NEXT_PUBLIC_AUTH0_AUDIENCE;
const need = (v: string | undefined, what: string): string => { if (!v) throw new Error(what); return v; };

const CACHE_KEY = "cashcan.profile.v1";
const readCache = (): Me | null => { try { const v = sessionStorage.getItem(CACHE_KEY); return v ? (JSON.parse(v) as Me) : null; } catch { return null; } };
const writeCache = (me: Me | null) => { try { if (me) sessionStorage.setItem(CACHE_KEY, JSON.stringify(me)); else sessionStorage.removeItem(CACHE_KEY); } catch { /* private mode */ } };

export type ProfileState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; me: Me };

/** The signed-in user's profile from the face API (wallet, face enrolled), via an Auth0 access token for that API. */
export function useProfile() {
  const { getAccessTokenSilently } = useAuth0();
  // Start from the last profile seen in this tab (set after a successful load) so clicking around shows no loading screen;
  // the real profile is always re-fetched in the background and replaces it.
  const [state, setState] = useState<ProfileState>({ status: "loading" });
  useEffect(() => { const c = readCache(); if (c) setState((s) => (s.status === "loading" ? { status: "ready", me: c } : s)); }, []);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const audience = need(AUDIENCE, "The face service is not configured (NEXT_PUBLIC_AUTH0_AUDIENCE is missing).");
        const token = need(await getAccessTokenSilently({ authorizationParams: { audience } }), "Could not get a login token for the face service.");
        const me = await getMe(token);
        writeCache(me);
        if (!cancelled) setState({ status: "ready", me });
      } catch (e) {
        if (!cancelled) setState((s) => (s.status === "ready" ? s : { status: "error", message: (e as Error).message || "We couldn't load your profile." }));
      }
    })();
    return () => { cancelled = true; };
  }, [getAccessTokenSilently, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);

  const setWallet = useCallback(async (wallet: string) => {
    const audience = need(AUDIENCE, "The face service is not configured.");
    const token = need(await getAccessTokenSilently({ authorizationParams: { audience } }), "Could not get a login token for the face service.");
    const updated = await saveWallet(token, wallet);
    setState((s) => {
      if (s.status !== "ready") return s;
      const me = { ...s.me, ...updated };
      writeCache(me);
      return { status: "ready", me };
    });
  }, [getAccessTokenSilently]);

  return { state, reload, setWallet };
}
