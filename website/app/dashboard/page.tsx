import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { getCurrentUser } from "@/lib/auth";
import DashboardView from "./DashboardView";
import "./dashboard.css";

export const metadata: Metadata = { title: "Dashboard — CashCan" };

export default async function DashboardPage({ searchParams }: { searchParams: Promise<{ welcome?: string }> }) {
  const user = await getCurrentUser();
  if (!user) redirect("/login?next=/dashboard");
  const { welcome } = await searchParams;
  return (
    <DashboardView
      firstName={user.name.split(" ")[0] || user.name}
      walletAddress={user.walletAddress}
      welcome={welcome === "1"}
    />
  );
}
