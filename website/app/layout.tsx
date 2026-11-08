import type { Metadata } from "next";
import { Inter, Space_Grotesk } from "next/font/google";
import Auth0ProviderWithNavigate from "@/components/Auth0ProviderWithNavigate";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
const spaceGrotesk = Space_Grotesk({ subsets: ["latin"], variable: "--font-space-grotesk", display: "swap" });

export const metadata: Metadata = {
  title: "CashCan — Smart bins that pay you to sort right",
  description:
    "A smart bin that knows Metro Vancouver's sorting rules, catches contaminated items with two cameras, and pays you in SOL for sorting correctly.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${spaceGrotesk.variable}`}>
      <body>
        <Auth0ProviderWithNavigate>{children}</Auth0ProviderWithNavigate>
      </body>
    </html>
  );
}
