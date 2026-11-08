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

export const Logo = ({ color = "#157A46" }: { color?: string }) => (
  <svg width="30" height="30" viewBox="0 0 32 32" fill="none" stroke={color} strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M7 9h18l-2 18H9z" />
    <path d="M5 9h22" />
    <path d="M12 9V6h8v3" />
    <path d="M13 15c1.5-1.5 4.5-1.5 6 0M16 14v8" />
  </svg>
);
