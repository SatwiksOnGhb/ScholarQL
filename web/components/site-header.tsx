import Link from "next/link";
import { Suspense } from "react";

import { ActiveNav } from "@/components/active-nav";
import { NavList } from "@/components/nav";

export function SiteHeader() {
  return (
    <header className="border-b bg-background">
      <div className="mx-auto flex h-14 w-full max-w-6xl items-center gap-6 px-4">
        <Link href="/" className="shrink-0 font-semibold tracking-tight">
          ScholarQL
        </Link>
        {/* usePathname() can't resolve on dynamic routes like /papers/[id] during
            prerendering, so the active-link nav needs a Suspense fallback */}
        <Suspense fallback={<NavList />}>
          <ActiveNav />
        </Suspense>
      </div>
    </header>
  );
}
