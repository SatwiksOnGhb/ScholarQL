import { Construction } from "lucide-react";
import type { ReactNode } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

const OWNERS = { A: "Person A", B: "Person B", C: "Person C" } as const;

/** Banner for pages that still show placeholder data. Delete it when the real page lands. */
export function PlaceholderNotice({
  owner,
  children,
}: {
  owner: keyof typeof OWNERS;
  children: ReactNode;
}) {
  return (
    <Alert className="mb-6">
      <Construction />
      <AlertTitle>Placeholder page · owner: {OWNERS[owner]}</AlertTitle>
      <AlertDescription>{children}</AlertDescription>
    </Alert>
  );
}
