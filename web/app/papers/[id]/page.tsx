import type { Metadata } from "next";
import { Suspense } from "react";

import { PageHeader } from "@/components/page-header";
import { PlaceholderNotice } from "@/components/placeholder-notice";
import { LoadingState } from "@/components/query-state";

import { PaperPreview } from "./paper-preview";

export const metadata: Metadata = { title: "Paper" };

// TODO(A): replace with the real paper page and citation explorer graph
export default function PaperPage({ params }: PageProps<"/papers/[id]">) {
  return (
    <>
      <PageHeader title="Paper" description="Details and citation chain for one paper." />
      <PlaceholderNotice owner="A">
        GET /papers/{"{id}"} and /citations serve the placeholder catalog until PostgreSQL is
        loaded.
      </PlaceholderNotice>
      {/* params is only known at request time, so read it inside a Suspense boundary */}
      <Suspense fallback={<LoadingState />}>
        {params.then(({ id }) => (
          <PaperPreview id={Number(id)} />
        ))}
      </Suspense>
    </>
  );
}
