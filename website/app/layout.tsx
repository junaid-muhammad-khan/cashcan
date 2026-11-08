import type { Metadata } from "next";
import { Inter, Space_Grotesk } from "next/font/google";
import WarmFaceApi from "@/components/WarmFaceApi";
import Auth0ProviderWithNavigate from "@/components/Auth0ProviderWithNavigate";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
const spaceGrotesk = Space_Grotesk({ subsets: ["latin"], variable: "--font-space-grotesk", display: "swap" });

export const metadata: Metadata = {
  title: "CashCan — Smart bins that pay you to sort right",
  description:
    "A smart bin that tracks what you throw away, shows you the right container by Metro Vancouver's rules, and pays you cash back in SOL for recycling correctly.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${spaceGrotesk.variable}`}>
      <body>
        <Auth0ProviderWithNavigate>
          <WarmFaceApi />
          {children}
        </Auth0ProviderWithNavigate>
      </body>
    </html>
  );
}
