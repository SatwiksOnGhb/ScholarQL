import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { PageHeader } from "@/components/page-header";
import { LoadingState } from "@/components/query-state";

import { PaperView } from "./paper-view";

export const metadata: Metadata = { title: "Paper" };

export default function PaperPage({ params }: PageProps<"/papers/[id]">) {
  return (
    <>
      <PageHeader title="Paper" description="Details and citation chain for one paper.">
        <Link href="/papers" className="text-sm underline underline-offset-4">
          All papers
        </Link>
      </PageHeader>
      {/* params is only known at request time, so read it inside a Suspense boundary */}
      <Suspense fallback={<LoadingState />}>
        {params.then(({ id }) => (
          <PaperView id={decodeURIComponent(id)} />
        ))}
      </Suspense>
    </>
  );
}
