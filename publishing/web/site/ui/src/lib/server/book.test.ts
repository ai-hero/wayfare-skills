// Copyright (c) 2026 A.I. Hero, Inc.
// All Rights Reserved.

import { readFileSync } from "node:fs";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { book } from "@/lib/book";
import { sealSession } from "@/lib/session";
import { resetLivenessCacheForTests } from "@/lib/server/auth";
import { chapterFor, evidenceFor, hasLiveSession } from "./book";

const SECRET = "test-secret"; // pragma: allowlist secret
const free = book.chapters.filter((c) => c.free);
const locked = book.chapters.filter((c) => !c.free);

function issuerSays(status: number) {
  vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status })));
}

function session(expiresAt = Date.now() + 60_000) {
  return sealSession({ expiresAt, accessToken: "AT" }, SECRET);
}

const yes = async () => true;
const never = async (): Promise<boolean> => {
  throw new Error("a free chapter must not ask for the session");
};

function file(dir: "chapters" | "evidence", slug: string): { free: boolean } {
  return JSON.parse(readFileSync(new URL(`../../data/book/${dir}/${slug}.json`, import.meta.url), "utf8"));
}

beforeEach(() => resetLivenessCacheForTests());
afterEach(() => vi.unstubAllGlobals());

describe("book sign-in gate", () => {
  it("has both free and locked chapters to test", () => {
    expect(free.length).toBeGreaterThan(0);
    expect(locked.length).toBeGreaterThan(0);
  });

  it("frees exactly chapters one and two, and the index agrees with every file", () => {
    expect(free.map((c) => c.n)).toEqual([1, 2]);
    for (const c of book.chapters) expect(file("chapters", c.slug).free).toBe(c.free);
    for (const c of book.evidence.chapters) expect(file("evidence", c.slug).free).toBe(c.free);
  });

  it("returns a locked chapter as its teaser and section titles only, without a session", async () => {
    for (const entry of locked) {
      const full = await chapterFor(entry.slug, yes);
      const shown = await chapterFor(entry.slug, () => hasLiveSession(undefined, SECRET));
      if (full?.locked !== false || shown?.locked !== true) throw new Error(`${entry.slug}: wrong view`);
      expect(shown.teaserHtml).toBeTruthy();
      expect(Object.keys(shown)).not.toContain("sources");
      expect(shown.sections.every((s) => Object.keys(s).sort().join() === "id,titleHtml")).toBe(true);
      const paragraphs = full.sections.flatMap((s) => s.blocks).flatMap((b) => (b.kind === "p" ? [b.html] : []));
      expect(paragraphs.length).toBeGreaterThan(1);
      for (const html of paragraphs.slice(1)) expect(JSON.stringify(shown)).not.toContain(html);
    }
  });

  it("returns the whole chapter with a sealed, live session", async () => {
    issuerSays(200);
    const signedIn = await hasLiveSession(await session(), SECRET);
    expect(signedIn).toBe(true);
    for (const entry of locked) {
      const shown = await chapterFor(entry.slug, async () => signedIn);
      expect(shown?.locked).toBe(false);
      expect(shown?.locked === false && shown.sections.some((s) => s.blocks.length > 0)).toBe(true);
    }
  });

  it("counts an unreachable issuer as signed in, and a 401 or 403 as signed out", async () => {
    issuerSays(503);
    expect(await hasLiveSession(await session(), SECRET)).toBe(true);
    resetLivenessCacheForTests();
    vi.stubGlobal("fetch", vi.fn(async () => {
      throw new TypeError("fetch failed");
    }));
    expect(await hasLiveSession(await session(), SECRET)).toBe(true);
    for (const status of [401, 403]) {
      resetLivenessCacheForTests();
      issuerSays(status);
      expect(await hasLiveSession(await session(), SECRET)).toBe(false);
    }
  });

  it("refuses an expired, foreign, garbage or revoked session", async () => {
    issuerSays(200);
    expect(await hasLiveSession(await session(Date.now() - 1), SECRET)).toBe(false);
    expect(await hasLiveSession(await session(), "another-secret")).toBe(false);
    expect(await hasLiveSession("garbage", SECRET)).toBe(false);
    resetLivenessCacheForTests();
    issuerSays(401);
    expect(await hasLiveSession(await session(), SECRET)).toBe(false);
  });

  it("returns free chapters whole without a session", async () => {
    for (const entry of free) {
      const shown = await chapterFor(entry.slug, never);
      expect(shown?.locked).toBe(false);
      expect(shown?.locked === false && shown.sections.some((s) => s.blocks.length > 0)).toBe(true);
    }
  });

  it("returns null for an unknown slug", async () => {
    expect(await chapterFor("no-such-chapter", yes)).toBeNull();
    expect(await evidenceFor("no-such-chapter", yes)).toBeNull();
  });

  it("chains chapters both ways", async () => {
    const slugs = book.chapters.map((c) => c.slug);
    for (const [i, slug] of slugs.entries()) {
      const chapter = await chapterFor(slug, yes);
      expect(chapter?.prev?.slug ?? null).toBe(slugs[i - 1] ?? null);
      expect(chapter?.next?.slug ?? null).toBe(slugs[i + 1] ?? null);
    }
  });
});

describe("evidence appendix gate", () => {
  const freeEvidence = book.evidence.chapters.filter((c) => c.free);
  const lockedEvidence = book.evidence.chapters.filter((c) => !c.free && c.count > 0);

  it("has both free and locked evidence to test", () => {
    expect(freeEvidence.length).toBeGreaterThan(0);
    expect(lockedEvidence.length).toBeGreaterThan(0);
  });

  it("returns no entries for locked evidence without a session", async () => {
    for (const entry of lockedEvidence) {
      const full = await evidenceFor(entry.slug, yes);
      const shown = await evidenceFor(entry.slug, () => hasLiveSession(undefined, SECRET));
      if (full?.locked !== false || shown?.locked !== true) throw new Error(`${entry.slug}: wrong view`);
      expect(shown.groups.every((g) => Object.keys(g).join() === "title")).toBe(true);
      const entries = full.groups.flatMap((g) => g.entries);
      for (const e of entries) expect(JSON.stringify(shown)).not.toContain(e.anchor);
    }
  });

  it("returns the entries with a sealed, live session", async () => {
    issuerSays(200);
    const signedIn = await hasLiveSession(await session(), SECRET);
    for (const entry of lockedEvidence) {
      const shown = await evidenceFor(entry.slug, async () => signedIn);
      expect(shown?.locked === false && shown.groups.some((g) => g.entries.length > 0)).toBe(true);
    }
  });

  it("returns a free chapter's evidence whole without a session", async () => {
    for (const entry of freeEvidence) {
      const shown = await evidenceFor(entry.slug, never);
      expect(shown?.locked).toBe(false);
      expect(shown?.count).toBe(entry.count);
    }
  });
});
