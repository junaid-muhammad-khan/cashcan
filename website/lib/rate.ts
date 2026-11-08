// SOL <-> CAD helpers. The rate itself comes from /api/rate (see app/api/rate/route.ts).
export interface Rate {
  cadPerSol: number;
  solPerCad: number;
  source: string;
  fetchedAt: string; // ISO time the server read the price
}

export const centsToCad = (cents: number) => cents / 100;
export const cadToSol = (cad: number, r: Rate) => cad / r.cadPerSol;
export const solToCad = (sol: number, r: Rate) => sol * r.cadPerSol;

// "C$", so an amount is never mistaken for US dollars.
export const fmtCad = (cad: number) => `C$${new Intl.NumberFormat("en-CA", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(cad)}`;
export const fmtSol = (sol: number) => (sol === 0 ? "0" : sol < 0.000001 ? "< 0.000001" : sol.toLocaleString("en-CA", { maximumFractionDigits: 6 }));

/** Parse what someone typed: "", "." and junk give null; otherwise a non-negative number. */
export function parseAmount(text: string): number | null {
  const n = Number(text.trim());
  return text.trim() === "" || !Number.isFinite(n) || n < 0 ? null : n;
}
