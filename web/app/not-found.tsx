import Link from "next/link";

export default function NotFound() {
  return (
    <div className="space-y-3 py-16 text-center">
      <h1 className="text-2xl font-semibold tracking-tight">Page not found</h1>
      <p className="text-muted-foreground">
        <Link href="/" className="underline underline-offset-4">
          Back to the home page
        </Link>
      </p>
    </div>
  );
}
