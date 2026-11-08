// Devnet balance of a wallet, for the dashboard. Public data, so no login; only a well-formed address is accepted.
import { PublicKey } from "@solana/web3.js";
import { lamportsToSol } from "@/lib/solana/convert";
import { getConnection } from "@/lib/solana/treasury";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const address = new URL(req.url).searchParams.get("address") ?? "";
  let key: PublicKey;
  try {
    if (!/^[1-9A-HJ-NP-Za-km-z]{32,44}$/.test(address)) throw new Error();
    key = new PublicKey(address);
  } catch {
    return Response.json({ error: "Not a Solana wallet address." }, { status: 400 });
  }
  try {
    const lamports = await getConnection().getBalance(key, "confirmed");
    return Response.json({ address, lamports, sol: lamportsToSol(lamports), cluster: "devnet" },
      { headers: { "Cache-Control": "private, max-age=15" } });
  } catch {
    return Response.json({ error: "Couldn't read the wallet balance from Solana devnet right now." }, { status: 502 });
  }
}
