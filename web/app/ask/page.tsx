import type { Metadata } from "next";

import { PageHeader } from "@/components/page-header";
import { PlaceholderNotice } from "@/components/placeholder-notice";

import { AskPreview } from "./ask-preview";

export const metadata: Metadata = { title: "Ask" };

// TODO(B): replace with the real Ask page (question box, SQL viewer, results table, feedback)
export default function AskPage() {
  return (
    <>
      <PageHeader
        title="Ask"
        description="Ask a question in plain English and see the SQL behind the answer."
      />
      <PlaceholderNotice owner="B">
        POST /ask returns a fixed placeholder answer until the NL-to-SQL engine is connected.
      </PlaceholderNotice>
      <AskPreview />
    </>
  );
}
