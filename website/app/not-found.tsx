import Link from "next/link";
import PageShell from "@/components/PageShell";

export default function NotFound() {
  return (
    <PageShell eyebrow="404" title="That page is not here." lede="The link may be old or mistyped. These will get you back on track.">
      <div className="cta-row" style={{ marginTop: 24 }}>
        <Link href="/" className="btn btn-primary">Home</Link>
        <Link href="/dashboard" className="btn btn-ghost">Dashboard</Link>
        <Link href="/prices" className="btn btn-ghost">Prices</Link>
      </div>
    </PageShell>
  );
}
