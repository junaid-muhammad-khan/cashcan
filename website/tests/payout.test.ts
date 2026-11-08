import { Keypair } from "@solana/web3.js";
import { describe, expect, it, vi } from "vitest";
import { handleGet, handlePost, type Deps } from "@/lib/payoutHandler";
import { PayoutError } from "@/lib/solana/payout";

const SECRET = "test-secret";
const WALLET = "9xQeWvG816bUx9EPjHmaT23yvVM2ZWbrrpZb9PusVFin";
const treasury = Keypair.generate();

function deps(over: Partial<Deps> = {}): Deps & { send: ReturnType<typeof vi.fn>; find: ReturnType<typeof vi.fn> } {
  return {
    secret: SECRET,
    connection: () => ({}) as never,               // never touched: find/send are mocked
    treasury: () => treasury,
    quote: async () => ({ cadPerSol: 100, source: "Test", fetchedAt: Date.now() }),
    find: vi.fn(async () => null),
    send: vi.fn(async () => "SIG123"),
    ...over,
  } as never;
}

const post = (body: unknown, auth: string | null = `Bearer ${SECRET}`) =>
  new Request("http://x/api/payout", { method: "POST", headers: { "content-type": "application/json", ...(auth ? { authorization: auth } : {}) },
    body: typeof body === "string" ? body : JSON.stringify(body) });
const good = { interaction_id: "i-1", to: WALLET, reward_cents: 5 };

describe("POST /api/payout", () => {
  it("needs the shared secret", async () => {
    const d = deps();
    expect((await handlePost(post(good, null), d)).status).toBe(401);
    expect((await handlePost(post(good, "Bearer wrong"), d)).status).toBe(401);
    expect((await handlePost(post(good, `Bearer ${SECRET}x`), d)).status).toBe(401);
    expect((await handlePost(post(good), deps({ secret: undefined }))).status).toBe(503);
    expect(d.send).not.toHaveBeenCalled();
  });

  it("validates the body and never sends to a bad wallet", async () => {
    const d = deps();
    for (const bad of [{ ...good, to: "nope" }, { ...good, to: "0OIl".repeat(10) }, { ...good, reward_cents: 0 }, { ...good, reward_cents: 2.5 },
      { ...good, reward_cents: 101 }, { ...good, reward_cents: "5" }, { ...good, interaction_id: "" }, { ...good, interaction_id: "a b" }]) {
      expect((await handlePost(post(bad), d)).status).toBe(400);
    }
    expect((await handlePost(post("not json"), d)).status).toBe(400);
    expect(d.send).not.toHaveBeenCalled();
  });

  it("converts cents at the live rate and sends once with the memo", async () => {
    const d = deps();
    const r = await handlePost(post(good), d);
    expect(r.status).toBe(200);
    expect(await r.json()).toEqual({ signature: "SIG123", lamports: 500_000, cad_per_sol: 100, rate_source: "Test", duplicate: false });
    expect(d.send).toHaveBeenCalledTimes(1);
    const [, , to, lamports, id] = d.send.mock.calls[0];
    expect(to.toBase58()).toBe(WALLET); expect(lamports).toBe(500_000); expect(id).toBe("i-1");
  });

  it("returns the existing transfer instead of paying twice", async () => {
    const d = deps({ find: vi.fn(async () => ({ signature: "OLD", lamports: 400_000 })) } as never);
    const body = await (await handlePost(post(good), d)).json();
    expect(body).toMatchObject({ signature: "OLD", lamports: 400_000, duplicate: true });
    expect(d.send).not.toHaveBeenCalled();
  });

  it("reports a low treasury clearly and keeps it retryable", async () => {
    const d = deps({ send: vi.fn(async () => { throw new PayoutError("Treasury balance too low for this payout", 503, "treasury_low"); }) } as never);
    const r = await handlePost(post(good), d);
    expect(r.status).toBe(503);
    expect(await r.json()).toMatchObject({ code: "treasury_low" });
  });

  it("does not pay without a rate", async () => {
    const d = deps({ quote: async () => null });
    expect((await handlePost(post(good), d)).status).toBe(503);
    expect(d.send).not.toHaveBeenCalled();
  });
});

describe("GET /api/payout (memo lookup)", () => {
  const get = (q: string, auth = `Bearer ${SECRET}`) => new Request(`http://x/api/payout?${q}`, { headers: { authorization: auth } });
  it("needs the secret and an id", async () => {
    expect((await handleGet(get("interaction_id=i-1", "Bearer no"), deps())).status).toBe(401);
    expect((await handleGet(get(""), deps())).status).toBe(400);
  });
  it("answers found / not found", async () => {
    expect(await (await handleGet(get("interaction_id=i-1"), deps())).json()).toEqual({ found: false });
    const d = deps({ find: vi.fn(async () => ({ signature: "S", lamports: 1 })) } as never);
    expect(await (await handleGet(get("interaction_id=i-1"), d)).json()).toEqual({ found: true, signature: "S", lamports: 1 });
  });
});
