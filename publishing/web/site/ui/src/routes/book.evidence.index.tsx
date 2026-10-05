// Copyright (c) 2026 A.I. Hero, Inc.
// All Rights Reserved.

import { createFileRoute } from "@tanstack/react-router";
import { BookEvidenceIndexPage } from "@/components/organisms/BookEvidencePage";
import { book } from "@/lib/book";
import { head } from "@/lib/head";

// Public: the appendix's own introduction and one link per chapter. Each
// chapter's entries sit behind the same gate as the chapter itself.
export const Route = createFileRoute("/book/evidence/")({
  head: () =>
    head({
      title: `Evidence · ${book.meta.title}`,
      description: book.meta.subtitle || book.meta.title,
      path: "/book/evidence",
      ogType: "website",
    }),
  component: () => (
    <BookEvidenceIndexPage
      meta={book.meta}
      introHtml={book.evidence.introHtml}
      chapters={book.evidence.chapters}
    />
  ),
});
