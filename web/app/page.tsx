// Placeholder home page for task 1. The real shell (navigation, pages) comes in task 4.
export default function Home() {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col justify-center gap-4 px-6 py-24">
      <h1 className="text-4xl font-semibold tracking-tight">ScholarQL</h1>
      <p className="text-lg text-zinc-600 dark:text-zinc-400">
        Ask questions about research papers in plain English.
      </p>
      <p className="text-sm text-zinc-500">
        API:{" "}
        <a className="underline" href={`${apiUrl}/docs`}>
          {apiUrl}/docs
        </a>
      </p>
    </main>
  );
}
