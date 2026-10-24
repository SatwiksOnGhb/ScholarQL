import type { Metadata } from "next";

import { PageHeader } from "@/components/page-header";
import { PlaceholderNotice } from "@/components/placeholder-notice";

import { SearchPreview } from "./search-preview";

export const metadata: Metadata = { title: "Search" };

export default function SearchPage() {
  return (
    <>
      <PageHeader
        title="Search"
        description="Find papers by meaning, then filter by year and venue."
      />
      <PlaceholderNotice owner="C">
        Keyword matching over the placeholder catalog. Vector search and filters arrive in task 8.
      </PlaceholderNotice>
      <SearchPreview />
    </>
  );
}
