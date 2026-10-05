// Copyright (c) 2026 A.I. Hero, Inc.
// All Rights Reserved.

import { expect, test } from "@playwright/test";
import index from "../ui/src/data/book/index.json";
import { readFileSync } from "node:fs";
import { join } from "node:path";

// The book's sign-in gate is enforced on the server: a locked chapter's text
// must not be in the HTML a visitor without a session receives.
const locked = index.chapters.find((c) => !c.free)!;
const posted = index.chapters.find((c) => c.url)!;

function secondParagraph(slug: string): string {
  const chapter = JSON.parse(
    readFileSync(join(__dirname, "../ui/src/data/book/chapters", `${slug}.json`), "utf-8"),
  );
  const paragraphs = chapter.sections
    .flatMap((s: { blocks: { kind: string; html?: string }[] }) => s.blocks)
    .filter((b: { kind: string }) => b.kind === "p");
  return paragraphs[1].html.replace(/<[^>]+>/g, "").slice(0, 60);
}

test("a locked chapter's HTML carries no body text, and is noindex and no-store", async ({ request }) => {
  const res = await request.get(`/book/${locked.slug}`);
  expect(res.status()).toBe(200);
  expect(res.headers()["cache-control"]).toContain("no-store");
  expect(res.headers()["vary"]).toContain("Cookie");
  const html = await res.text();
  expect(html).not.toContain(secondParagraph(locked.slug));
  expect(html).toContain('content="noindex, nofollow"');
  expect(html).toContain("Sign in to continue reading.");
});

test("a chapter published as a blog post redirects to it, and the post carries the chapter", async ({ request }) => {
  const res = await request.get(`/book/${posted.slug}`, { maxRedirects: 0 });
  expect(res.status()).toBe(308);
  expect(res.headers()["location"]).toBe(posted.url);
  const html = await (await request.get(posted.url!)).text();
  expect(html).toContain(secondParagraph(posted.slug));
  expect(html).toContain('href="/book"');
});

function firstFinding(slug: string): string {
  const evidence = JSON.parse(
    readFileSync(join(__dirname, "../ui/src/data/book/evidence", `${slug}.json`), "utf-8"),
  );
  const block = evidence.groups
    .flatMap((g: { entries: { blocks: { html?: string }[] }[] }) => g.entries)
    .flatMap((e: { blocks: { html?: string }[] }) => e.blocks)
    .find((b: { html?: string }) => b.html);
  return block.html.replace(/<[^>]+>/g, "").slice(0, 60);
}

test("locked evidence carries no finding text, and is noindex and no-store", async ({ request }) => {
  const ev = index.evidence.chapters.find((c) => !c.free && c.count > 0)!;
  const res = await request.get(`/book/evidence/${ev.slug}`);
  expect(res.status()).toBe(200);
  expect(res.headers()["cache-control"]).toContain("no-store");
  const html = await res.text();
  expect(html).not.toContain(firstFinding(ev.slug));
  expect(html).toContain('content="noindex, nofollow"');
  expect(html).toContain("Sign in to continue reading.");
});

test("a free chapter's evidence is public, with its charts", async ({ page }) => {
  const ev = index.evidence.chapters.find((c) => c.free && c.count > 0)!;
  await page.goto(`/book/evidence/${ev.slug}`);
  await expect(page.getByText(firstFinding(ev.slug), { exact: false })).toBeVisible();
  await expect(page.locator("article img").first()).toBeVisible();
  await page.goto("/book/evidence");
  await expect(page.getByRole("link", { name: new RegExp(ev.title) })).toBeVisible();
});
