import Link from "next/link";
import { LogoMark } from "./icons";

/** Shared site footer (home and account pages): logo mark, one-line note, a few links. */
export default function SiteFooter() {
  return (
    <footer className="footer">
      <div className="container">
        <span className="footer-brand">
          <Link href="/" className="logo footer-logo"><LogoMark size={24} /><span>cashcan</span></Link>
          <span className="footer-note">a HackCamp 2026 prototype. Payouts use Solana devnet test tokens only.</span>
        </span>
        <nav aria-label="Footer">
          <Link href="/how-it-works">How it works</Link><Link href="/prices">Prices</Link><Link href="/privacy">Privacy</Link><Link href="/terms">Terms</Link><Link href="/login">Log in</Link>
        </nav>
      </div>
    </footer>
  );
}
