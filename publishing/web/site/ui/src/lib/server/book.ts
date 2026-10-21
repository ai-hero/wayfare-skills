// Copyright (c) 2026 A.I. Hero, Inc.
// All Rights Reserved.

// Server-only: the book's chapter bodies and the sign-in gate in front of them.
// Never import from client code. A locked chapter's JSON must be loaded only
// through this module: beyond its opening paragraph, its text is then never in
// a client chunk, the SSR HTML, or a server-function answer unless the request
// carries a live session. Only a free chapter may be imported directly, as the
// generated blog posts do.

import { unsealSession } from "@/lib/session";
import { checkLiveness, sessionSecret } from "@/lib/server/auth";
import type { Chapter, ChapterFile, EvidenceChapter, EvidenceFile } from "@/lib/book";

const chapters = import.meta.glob<ChapterFile>("../../data/book/chapters/*.json", {
  import: "default",
});

const evidence = import.meta.glob<EvidenceFile>("../../data/book/evidence/*.json", {
  import: "default",
});

/**
 * The same question /auth/me answers: a session cookie we sealed, unexpired,
 * that the issuer has not revoked. "unreachable" counts as signed in, as it
 * does there: an issuer blip must not sign every reader out mid-chapter, and
 * the sealed expiry still bounds it.
 */
export async function hasLiveSession(
  raw: string | undefined,
  secret = sessionSecret(),
): Promise<boolean> {
  if (!raw) return false;
  const session = await unsealSession(raw, secret);
  if (!session) return false;
  return (await checkLiveness(session.accessToken)) !== "revoked";
}

/**
 * A chapter as this request may see it: whole when it is free or the reader is
 * signed in; otherwise its title, section titles and opening paragraph only.
 * Null when no chapter has that slug. Only the chapter's own file says whether
 * it is free, and `signedIn` is asked only for a chapter that is not.
 */
export async function chapterFor(
  slug: string,
  signedIn: () => Promise<boolean>,
): Promise<Chapter | null> {
  const load = chapters[`../../data/book/chapters/${slug}.json`];
  if (!load) return null;
  const chapter = await load();
  if (chapter.free || (await signedIn())) return { ...chapter, locked: false };
  const { sections, notes: _notes, sources: _sources, ...head } = chapter;
  const first = sections.flatMap((s) => s.blocks).find((b) => b.kind === "p");
  return {
    ...head,
    locked: true,
    teaserHtml: first && "html" in first ? first.html : "",
    sections: sections.map(({ id, titleHtml }) => ({ id, titleHtml })),
  };
}

/**
 * A chapter's evidence appendix as this request may see it: whole when its
 * chapter is free or the reader is signed in; otherwise the group titles and
 * entry count only. Null when no chapter has that slug.
 */
export async function evidenceFor(
  slug: string,
  signedIn: () => Promise<boolean>,
): Promise<EvidenceChapter | null> {
  const load = evidence[`../../data/book/evidence/${slug}.json`];
  if (!load) return null;
  const chapter = await load();
  if (chapter.free || (await signedIn())) return { ...chapter, locked: false };
  const { groups, ...head } = chapter;
  return { ...head, locked: true, groups: groups.map(({ title }) => ({ title })) };
}
