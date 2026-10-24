import type { Metadata } from "next";

import { PageHeader } from "@/components/page-header";
import { PlaceholderNotice } from "@/components/placeholder-notice";

import { ReviewersPreview } from "./reviewers-preview";

export const metadata: Metadata = { title: "Reviewers" };

export default function ReviewersPage() {
  return (
    <>
      <PageHeader
        title="Reviewer finder"
        description="Suggest reviewers for an abstract, without conflicts of interest."
      />
      <PlaceholderNotice owner="C">
        Placeholder suggestions from the fake catalog. Profile matching and the co-author check
        arrive in task 9.
      </PlaceholderNotice>
      <ReviewersPreview />
    </>
  );
}
