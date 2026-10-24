import type { Metadata } from "next";
import Link from "next/link";

import { PageHeader } from "@/components/page-header";
import { PlaceholderNotice } from "@/components/placeholder-notice";

import { TrendsPreview } from "./trends-preview";

export const metadata: Metadata = { title: "Papers" };

// TODO(A): replace with the trends dashboard (topic trends chart, rising papers)
export default function PapersPage() {
  return (
    <>
      <PageHeader
        title="Papers"
        description="Topic trends, influential papers and citation chains."
      />
      <PlaceholderNotice owner="A">
        GET /trends returns made-up counts until the PostgreSQL views exist.
      </PlaceholderNotice>
      <p className="mb-4 text-sm">
        Example paper page:{" "}
        <Link href="/papers/1001" className="underline underline-offset-4">
          /papers/1001
        </Link>{" "}
        (fake ID from the placeholder catalog)
      </p>
      <TrendsPreview />
    </>
  );
}
