"use client";

import { Auth0Provider, type AppState } from "@auth0/auth0-react";
import { useRouter } from "next/navigation";

// This is a Client Component so the SDK can keep auth state (tokens, user) in the
// browser. It's still rendered once on the server for the initial HTML, so it must
// never read `window` directly — only behind a `typeof window` check.
export default function Auth0ProviderWithNavigate({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const domain = process.env.NEXT_PUBLIC_AUTH0_DOMAIN!;
  const clientId = process.env.NEXT_PUBLIC_AUTH0_CLIENT_ID!;

  const onRedirectCallback = (appState?: AppState) => {
    router.replace(appState?.returnTo ?? "/dashboard");
  };

  return (
    <Auth0Provider
      domain={domain}
      clientId={clientId}
      authorizationParams={{
        redirect_uri: typeof window !== "undefined" ? window.location.origin : undefined,
        // Access tokens for the face API (face_api checks AUTH0_AUDIENCE). Optional for local dev.
        ...(process.env.NEXT_PUBLIC_AUTH0_AUDIENCE ? { audience: process.env.NEXT_PUBLIC_AUTH0_AUDIENCE } : {}),
      }}
      onRedirectCallback={onRedirectCallback}
    >
      {children}
    </Auth0Provider>
  );
}
