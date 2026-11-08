import { describe, expect, it } from "vitest";
import { DB_PAUSED, isDbPaused, parseDetail } from "@/lib/errors";

describe("parseDetail", () => {
  it("reads a plain string detail", () => {
    expect(parseDetail({ detail: "Missing bearer token." }, "x")).toEqual({ message: "Missing bearer token." });
  });
  it("reads the database-paused object the API sends with a 503", () => {
    const body = { detail: { code: DB_PAUSED, daily_limit: true, message: "CashCan's database isn't available right now." } };
    expect(parseDetail(body, "x")).toEqual({ message: "CashCan's database isn't available right now.", code: DB_PAUSED });
  });
  it("falls back when there is nothing usable", () => {
    for (const body of [null, {}, { detail: 5 }, { detail: {} }, { detail: { message: 3 } }]) {
      expect(parseDetail(body, "fallback").message).toBe("fallback");
    }
  });
});

describe("isDbPaused", () => {
  it("is true only for the database-paused code", () => {
    expect(isDbPaused({ code: DB_PAUSED })).toBe(true);
    expect(isDbPaused({ code: "duplicate_face" })).toBe(false);
    expect(isDbPaused(new Error("x"))).toBe(false);
    expect(isDbPaused(null)).toBe(false);
  });
});
