"use client";

import Link from "next/link";
import { useAuth0 } from "@auth0/auth0-react";
import styles from "./AuthPanel.module.css";
import { FaceScan, GoogleG } from "./icons";

type Props = {
  mode: "login" | "signup";
  returnTo: string;
};

const COPY = {
  login: {
    heading: "Welcome back",
    subtitle: "Log in to see your drops, rewards and wallet.",
    footerText: "New to CashCan?",
    footerLinkText: "Create an account",
    footerHref: "/signup",
  },
  signup: {
    heading: "Create your account",
    subtitle: "Free to join. Earn devnet SOL every time you sort right.",
    footerText: "Already have an account?",
    footerLinkText: "Log in",
    footerHref: "/login",
  },
};

export default function AuthPanel({ mode, returnTo }: Props) {
  const { isLoading, loginWithRedirect } = useAuth0();
  const copy = COPY[mode];
  const screenHint = mode === "signup" ? { screen_hint: "signup" as const } : {};

  const continueWithGoogle = () =>
    loginWithRedirect({
      authorizationParams: { connection: "google-oauth2", ...screenHint },
      appState: { returnTo },
    });

  const continueWithEmail = () =>
    loginWithRedirect({
      authorizationParams: { ...screenHint },
      appState: { returnTo },
    });

  return (
    <div className={styles.panel}>
      <div className={styles.inner}>
        <h1 className={styles.heading}>{copy.heading}</h1>
        <p className={styles.subtitle}>{copy.subtitle}</p>

        <div className={styles.actions}>
          <button type="button" className={styles.googleBtn} disabled={isLoading} onClick={continueWithGoogle}>
            <GoogleG />
            Continue with Google
          </button>

          <div className={styles.divider} aria-hidden="true">
            <span />or<span />
          </div>

          <button type="button" className={styles.emailBtn} disabled={isLoading} onClick={continueWithEmail}>
            Continue with email
          </button>
          <p className={styles.hint}>Password, magic link or passkey.</p>
        </div>

        <div className={styles.faceCard}>
          <div className={styles.faceIcon}>
            <FaceScan size={20} />
          </div>
          <div>
            <b>At a bin?</b>
            <p>Step up to the camera. Face match logs you in, no password needed.</p>
          </div>
        </div>

        <p className={styles.footer}>
          {copy.footerText} <Link href={copy.footerHref} className={styles.link}>{copy.footerLinkText}</Link>
        </p>
      </div>
    </div>
  );
}
