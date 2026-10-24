import type { Metadata } from "next";

import { PageHeader } from "@/components/page-header";

import { ReviewerFinder } from "./reviewer-finder";

export const metadata: Metadata = { title: "Reviewers" };

export default function ReviewersPage() {
  return (
    <>
      <PageHeader
        title="Reviewer finder"
        description="Paste an abstract to find qualified reviewers. Co-authors and colleagues of the submitting authors are left out."
      />
      <ReviewerFinder />
    </>
  );
}
