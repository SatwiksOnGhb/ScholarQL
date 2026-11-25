import type { Metadata } from "next";

import { PageHeader } from "@/components/page-header";

import { AskWorkbench } from "./ask-workbench";

export const metadata: Metadata = { title: "Ask" };

export default function AskPage() {
  return (
    <>
      <PageHeader
        title="Ask"
        description="Ask a question in plain English. ScholarQL answers with SQL over PostgreSQL, ranks papers by meaning over MongoDB, or combines both, and shows its work."
      />
      <AskWorkbench />
    </>
  );
}
