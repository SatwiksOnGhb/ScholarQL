import Link from "next/link";

import { NAV_ITEMS } from "@/components/nav";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

import { ApiStatus } from "./api-status";

export default function Home() {
  return (
    <div className="space-y-10">
      <section className="space-y-3 pt-6">
        <h1 className="text-4xl font-semibold tracking-tight">ScholarQL</h1>
        <p className="max-w-2xl text-lg text-muted-foreground">
          Ask questions about research papers in plain English. Get exact answers, with the SQL
          that produced them.
        </p>
        <ApiStatus />
      </section>

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {NAV_ITEMS.map(({ href, label, description, icon: Icon }) => (
          <Link key={href} href={href} className="group">
            <Card className="h-full transition-colors group-hover:bg-muted/50">
              <CardHeader>
                <Icon className="mb-2 size-5 text-muted-foreground" />
                <CardTitle>{label}</CardTitle>
                <CardDescription>{description}</CardDescription>
              </CardHeader>
            </Card>
          </Link>
        ))}
      </section>
    </div>
  );
}
