import {
  ChartColumn,
  FileText,
  type LucideIcon,
  MessageSquareText,
  Search,
  Users,
} from "lucide-react";
import Link from "next/link";

import { cn } from "@/lib/utils";

export type NavItem = {
  href: string;
  label: string;
  description: string;
  icon: LucideIcon;
};

export const NAV_ITEMS: NavItem[] = [
  {
    href: "/ask",
    label: "Ask",
    description: "Ask a question in plain English and see the SQL behind the answer.",
    icon: MessageSquareText,
  },
  {
    href: "/search",
    label: "Search",
    description: "Find papers by meaning, then filter by year and venue.",
    icon: Search,
  },
  {
    href: "/papers",
    label: "Papers",
    description: "Topic trends, influential papers and citation chains.",
    icon: FileText,
  },
  {
    href: "/reviewers",
    label: "Reviewers",
    description: "Suggest reviewers for an abstract, without conflicts of interest.",
    icon: Users,
  },
  {
    href: "/admin",
    label: "Analytics",
    description: "Accuracy, latency and the most-asked questions.",
    icon: ChartColumn,
  },
];

/** Plain nav list; `activePath` highlights the current section (omit it for no highlight). */
export function NavList({ activePath }: { activePath?: string }) {
  return (
    <nav className="-mx-1 flex items-center gap-1 overflow-x-auto">
      {NAV_ITEMS.map(({ href, label }) => {
        const active = activePath === href || activePath?.startsWith(`${href}/`);
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "rounded-md px-2.5 py-1.5 text-sm whitespace-nowrap text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
              active && "bg-muted font-medium text-foreground",
            )}
          >
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
