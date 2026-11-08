"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type CameraState = "idle" | "starting" | "on" | "denied" | "unavailable";

/** Webcam stream for a <video>, plus a helper that grabs the current frame as a JPEG. */
export function useCamera() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [state, setState] = useState<CameraState>("idle");

  const stop = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setState((s) => (s === "on" || s === "starting" ? "idle" : s));
  }, []);

  const start = useCallback(async () => {
    if (!navigator.mediaDevices?.getUserMedia) { setState("unavailable"); return false; }
    setState("starting");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play().catch(() => undefined);
      }
      setState("on");
      return true;
    } catch (err) {
      const name = (err as DOMException)?.name;
      setState(name === "NotAllowedError" || name === "SecurityError" ? "denied" : "unavailable");
      return false;
    }
  }, []);

  // Grabs the raw (un-mirrored) frame: the face API assumes "left" is the person's own left.
  const capture = useCallback(async (): Promise<Blob | null> => {
    const v = videoRef.current;
    if (!v || !v.videoWidth) return null;
    const c = document.createElement("canvas");
    c.width = v.videoWidth;
    c.height = v.videoHeight;
    c.getContext("2d")!.drawImage(v, 0, 0);
    return new Promise((resolve) => c.toBlob((b) => resolve(b), "image/jpeg", 0.92));
  }, []);

  useEffect(() => stop, [stop]);

  return { videoRef, state, start, stop, capture };
}
