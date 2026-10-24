import type { Metadata } from "next";

import { PageHeader } from "@/components/page-header";
import { PlaceholderNotice } from "@/components/placeholder-notice";

import { StatsPreview } from "./stats-preview";

export const metadata: Metadata = { title: "Analytics" };

export default function AdminPage() {
  return (
    <>
      <PageHeader title="Analytics" description="Accuracy, latency and the most-asked questions." />
      <PlaceholderNotice owner="C">
        Fixed placeholder numbers. Aggregations over query_logs and charts arrive in task 11.
      </PlaceholderNotice>
      <StatsPreview />
    </>
  );
}
