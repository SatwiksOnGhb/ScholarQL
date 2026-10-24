import type { Metadata } from "next";

import { PageHeader } from "@/components/page-header";

import { AnalyticsDashboard } from "./analytics-dashboard";

export const metadata: Metadata = { title: "Analytics" };

export default function AdminPage() {
  return (
    <>
      <PageHeader
        title="Analytics"
        description="How the question engine is used and how often it gets answers right."
      />
      <AnalyticsDashboard />
    </>
  );
}
