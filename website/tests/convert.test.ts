import { describe, expect, it } from "vitest";
import { centsToLamports, memoMatches, memoFor } from "@/lib/solana/convert";

describe("centsToLamports", () => {
  it("converts CAD cents to lamports at the given rate", () => {
    expect(centsToLamports(5, 100)).toBe(500_000);          // C$0.05 at C$100/SOL = 0.0005 SOL
    expect(centsToLamports(5, 126.474428)).toBe(395_337);   // 395,336.6 rounded to the nearest lamport
    expect(centsToLamports(100, 1)).toBe(1_000_000_000);
  });
  it("refuses bad input", () => {
    for (const c of [0, -5, 1.5, NaN]) expect(() => centsToLamports(c, 100)).toThrow();
    for (const r of [0, -1, NaN, Infinity]) expect(() => centsToLamports(5, r)).toThrow();
  });
});

describe("memoMatches", () => {
  it("finds the exact memo in the RPC memo field", () => {
    expect(memoMatches("[14] cashcan:abc", memoFor("abc"))).toBe(true);
    expect(memoMatches("[3] foo; [14] cashcan:abc", memoFor("abc"))).toBe(true);
    expect(memoMatches("[15] cashcan:abcd", memoFor("abc"))).toBe(false);   // a longer id is not a match
    expect(memoMatches(null, memoFor("abc"))).toBe(false);
  });
});
