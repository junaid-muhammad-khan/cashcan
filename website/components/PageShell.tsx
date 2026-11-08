import SiteFooter from "./SiteFooter";
import SiteNav from "./SiteNav";

/** Frame for the plain content pages (prices, how it works, privacy...): site header, a title block, content, site footer. */
export default function PageShell({ eyebrow, title, lede, children }: { eyebrow: string; title: string; lede?: string; children: React.ReactNode }) {
  return (
    <>
      <div className="page-top"><SiteNav /></div>
      <main className="page container">
        <div className="eyebrow">{eyebrow}</div>
        <h1 className="page-title">{title}</h1>
        {lede && <p className="section-lede page-lede">{lede}</p>}
        {children}
      </main>
      <SiteFooter />
    </>
  );
}
