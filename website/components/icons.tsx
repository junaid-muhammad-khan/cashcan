type P = { size?: number; color?: string; strokeWidth?: number };

const base = (size: number, color: string, sw: number) => ({
  width: size,
  height: size,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: color,
  strokeWidth: sw,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
});

export const Check = ({ size = 16, color = "#157A46", strokeWidth = 2.4 }: P) => (
  <svg {...base(size, color, strokeWidth)}><path d="M5 12l5 5L20 7" /></svg>
);
export const Person = ({ size = 20, color = "#157A46", strokeWidth = 2 }: P) => (
  <svg {...base(size, color, strokeWidth)}><circle cx="12" cy="8" r="4" /><path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6" /></svg>
);
export const Pin = ({ size = 22, color = "#157A46", strokeWidth = 2 }: P) => (
  <svg {...base(size, color, strokeWidth)}><path d="M12 21s-7-6.2-7-12a7 7 0 0114 0c0 5.8-7 12-7 12z" /><circle cx="12" cy="9" r="2.5" /></svg>
);
export const Drop = ({ size = 22, color = "#8A5A00", strokeWidth = 2 }: P) => (
  <svg {...base(size, color, strokeWidth)}><path d="M12 3c3 4 6 7 6 11a6 6 0 01-12 0c0-4 3-7 6-11z" /></svg>
);
export const Coin = ({ size = 22, color = "#2C5F8A", strokeWidth = 2 }: P) => (
  <svg {...base(size, color, strokeWidth)}>
    <circle cx="12" cy="12" r="9" />
    <path d="M14.5 9.5c-.5-1-1.5-1.5-2.5-1.5-1.4 0-2.5.8-2.5 2s1.1 1.6 2.5 2 2.5.8 2.5 2-1.1 2-2.5 2c-1 0-2-.5-2.5-1.5M12 6.5v1.5M12 16v1.5" />
  </svg>
);

export const GoogleG = ({ size = 18 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" aria-hidden="true">
    <path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9.1 3.6l6.8-6.8C35.9 2.4 30.5 0 24 0 14.6 0 6.5 5.4 2.6 13.2l7.9 6.1C12.3 13.1 17.6 9.5 24 9.5z" />
    <path fill="#4285F4" d="M46.5 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.6c-.5 2.9-2.2 5.4-4.6 7l7.4 5.7c4.3-4 6.8-9.9 6.8-17.2z" />
    <path fill="#FBBC05" d="M10.5 19.3a14.5 14.5 0 010-10.6l-7.9-6.1a24 24 0 000 22.8l7.9-6.1z" />
    <path fill="#34A853" d="M24 48c6.5 0 11.9-2.1 15.9-5.8l-7.4-5.7c-2.1 1.4-4.8 2.3-8.5 2.3-6.4 0-11.7-3.6-13.6-9.3l-7.9 6.1C6.5 42.6 14.6 48 24 48z" />
  </svg>
);

export const FaceScan = ({ size = 20, color = "#2F8F5B", strokeWidth = 2 }: P) => (
  <svg {...base(size, color, strokeWidth)}>
    <path d="M4 8V6a2 2 0 012-2h2" />
    <path d="M20 8V6a2 2 0 00-2-2h-2" />
    <path d="M4 16v2a2 2 0 002 2h2" />
    <path d="M20 16v2a2 2 0 01-2 2h-2" />
    <circle cx="9" cy="11" r="1" fill={color} stroke="none" />
    <circle cx="15" cy="11" r="1" fill={color} stroke="none" />
    <path d="M9 15c1 .8 3 .8 4 0" />
  </svg>
);

export const Logo = ({ color = "#157A46" }: { color?: string }) => (
  <svg width="30" height="30" viewBox="0 0 32 32" fill="none" stroke={color} strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M7 9h18l-2 18H9z" />
    <path d="M5 9h22" />
    <path d="M12 9V6h8v3" />
    <path d="M13 15c1.5-1.5 4.5-1.5 6 0M16 14v8" />
  </svg>
);

/** The app mark: white bin on the brand green, same as the browser-tab icon (app/icon.svg). */
export const LogoMark = ({ size = 32 }: { size?: number }) => (
  <span className="logo-mark" style={{ width: size, height: size }} aria-hidden="true">
    <svg width={size * 0.69} height={size * 0.69} viewBox="0 0 32 32" fill="none" stroke="#fff" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M7 9h18l-2 18H9z" />
      <path d="M5 9h22" />
      <path d="M12 9V6h8v3" />
      <path d="M13 15c1.5-1.5 4.5-1.5 6 0M16 14v8" />
    </svg>
  </span>
);
