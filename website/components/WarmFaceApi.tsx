"use client";

import { useEffect } from "react";
import { FACE_API } from "@/lib/faceApi";

// The face service sleeps when idle and takes ~20 s to wake up (start + load models). Poke it once per browser session as
// soon as any page loads, so by the time someone reaches /enroll it is already warm. Fire and forget; failures don't matter.
export default function WarmFaceApi() {
  useEffect(() => {
    try {
      if (sessionStorage.getItem("cashcan.warm")) return;
      sessionStorage.setItem("cashcan.warm", "1");
    } catch { /* private mode: warm anyway */ }
    fetch(`${FACE_API}/warm`, { cache: "no-store" }).catch(() => undefined);
  }, []);
  return null;
}
