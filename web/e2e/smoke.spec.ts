import { expect, type Page, test } from "@playwright/test";

// Smoke tests: every page renders and each main flow gets an answer from the API.
// PostgreSQL holds B's 353-paper pilot (db/init); MongoDB starts empty, so semantic search
// and the reviewer finder show their empty or "unavailable" states, which still proves the
// web -> API -> database wiring works.

const PAGES = [
  { path: "/ask", heading: "Ask" },
  { path: "/search", heading: "Search" },
  { path: "/papers", heading: "Papers" },
  { path: "/reviewers", heading: "Reviewer finder" },
  { path: "/admin", heading: "Analytics" },
];

/** Fail the test on uncaught browser errors (a crashed React tree, a bad import). */
function failOnPageErrors(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (err) => errors.push(err.message));
  return () => expect(errors, "uncaught errors in the browser").toEqual([]);
}

test("home page shows the API and both databases as healthy", async ({ page }) => {
  const check = failOnPageErrors(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "ScholarQL" })).toBeVisible();
  await expect(page.getByText(/API ok · PostgreSQL ok · MongoDB ok/)).toBeVisible();
  check();
});

for (const { path, heading } of PAGES) {
  test(`${path} renders`, async ({ page }) => {
    const check = failOnPageErrors(page);
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
    check();
  });
}

test("navigation links reach every section", async ({ page }) => {
  await page.goto("/");
  for (const { path, heading } of PAGES) {
    await page.getByRole("navigation").first().getByRole("link", { name: heading.split(" ")[0] }).click();
    await expect(page).toHaveURL(new RegExp(`${path}$`));
    await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
  }
});

test("ask: a SQL question gets an answer and feedback is saved", async ({ page }) => {
  const check = failOnPageErrors(page);
  await page.goto("/ask");
  await page.getByRole("textbox", { name: "Question" }).fill("Find arXiv paper 2305.14314");
  const [response] = await Promise.all([
    page.waitForResponse((r) => r.url().endsWith("/ask") && r.request().method() === "POST"),
    page.getByRole("button", { name: "Ask", exact: true }).click(),
  ]);
  expect(response.status()).toBe(200);
  const body = await response.json();
  expect(body.route).toBe("sql");
  await expect(page.getByLabel("Generated SQL")).toContainText("2305.14314");
  await expect(page.getByRole("table", { name: "Results" })).toContainText("QLoRA");

  // query_id is set when the answer was logged to MongoDB
  if (body.query_id) {
    const [saved] = await Promise.all([
      page.waitForResponse((r) => r.url().endsWith("/feedback")),
      page.getByRole("button", { name: "Yes" }).click(),
    ]);
    expect(saved.status()).toBe(200);
    await expect(page.getByRole("status")).toContainText("saved as correct");
  }
  check();
});

test("search: a query returns results, an empty state or a handled error", async ({ page }) => {
  const check = failOnPageErrors(page);
  await page.goto("/search");
  await page.getByRole("textbox", { name: "Search papers" }).fill("graph neural networks for molecules");
  const [response] = await Promise.all([
    page.waitForResponse((r) => new URL(r.url()).pathname === "/search"),
    page.getByRole("button", { name: "Search", exact: true }).click(),
  ]);
  await expect(page).toHaveURL(/[?&]q=graph/);
  expect([200, 503]).toContain(response.status());
  // Scoped to <main>: Next.js adds its own role="alert" route announcer outside it, and
  // first() because an empty-state and a list can't both be required at once
  const main = page.getByRole("main");
  await expect(
    main
      .getByRole("list", { name: "Search results" })
      .or(main.getByText("No papers matched."))
      .or(main.getByRole("alert"))
      .first(),
  ).toBeVisible();
  check();
});

test("reviewers: an abstract returns suggestions, an empty state or a handled error", async ({
  page,
}) => {
  const check = failOnPageErrors(page);
  await page.goto("/reviewers");
  await page.getByRole("button", { name: "Use an example" }).click();
  const [response] = await Promise.all([
    page.waitForResponse((r) => r.url().endsWith("/reviewers") && r.request().method() === "POST"),
    page.getByRole("button", { name: "Find reviewers" }).click(),
  ]);
  expect([200, 503]).toContain(response.status());
  const results = page.getByRole("region", { name: "Suggested reviewers" });
  await expect(
    results
      .getByRole("listitem")
      .first()
      .or(results.getByText("No suitable reviewers found."))
      .or(results.getByRole("alert")),
  ).toBeVisible();
  check();
});

test("papers: the library lists pilot papers and opens a paper page", async ({ page }) => {
  const check = failOnPageErrors(page);
  await page.goto("/papers");
  const first = page.getByRole("list", { name: "Papers" }).getByRole("link").first();
  const title = await first.innerText();
  await first.click();
  await expect(page).toHaveURL(/\/papers\/W\d+$/);
  await expect(page.getByRole("heading", { level: 2, name: title })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Citation explorer" })).toBeVisible();
  check();
});

test("analytics: stats load (dashboard or empty state)", async ({ page }) => {
  const check = failOnPageErrors(page);
  const statsResponse = page.waitForResponse((r) => r.url().includes("/admin/stats"));
  await page.goto("/admin");
  expect((await statsResponse).status()).toBe(200);
  await expect(
    page.getByText("Accuracy by route").or(page.getByText("No questions logged in this window yet.")),
  ).toBeVisible();
  check();
});
