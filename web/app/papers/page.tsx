import type { Metadata } from "next";
import { Suspense } from "react";

import { PageHeader } from "@/components/page-header";
import { LoadingState } from "@/components/query-state";

import { PaperBrowser } from "./paper-browser";
import { TrendsChart } from "./trends-chart";

export const metadata: Metadata = { title: "Papers" };

export default function PapersPage() {
  return (
    <>
      <PageHeader
        title="Papers"
        description="Topic trends, the most influential papers, and each paper's citation chain."
      />
      <div className="space-y-10">
        <TrendsChart />
        <Suspense fallback={<LoadingState />}>
          <PaperBrowser />
        </Suspense>
      </div>
    </>
  );
}
