import type { Metadata } from "next";
import { Suspense } from "react";

import { PageHeader } from "@/components/page-header";
import { LoadingState } from "@/components/query-state";

import { SearchView } from "./search-view";

export const metadata: Metadata = { title: "Search" };

export default function SearchPage() {
  return (
    <>
      <PageHeader
        title="Search"
        description="Find papers by meaning, not just keywords. Narrow by year and venue."
      />
      {/* SearchView reads the query from the URL, which is only known at request time */}
      <Suspense fallback={<LoadingState rows={2} />}>
        <SearchView />
      </Suspense>
    </>
  );
}
