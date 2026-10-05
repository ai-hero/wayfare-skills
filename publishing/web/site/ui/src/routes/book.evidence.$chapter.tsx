// Copyright (c) 2026 A.I. Hero, Inc.
// All Rights Reserved.

import { createFileRoute, notFound } from "@tanstack/react-router";
import { BookEvidencePage } from "@/components/organisms/BookEvidencePage";
import { book, getEvidence, spelled } from "@/lib/book";
import { head } from "@/lib/head";

export const Route = createFileRoute("/book/evidence/$chapter")({
  loader: async ({ params }) => {
    const evidence = await getEvidence({ data: params.chapter });
    if (!evidence) throw notFound();
    return evidence;
  },
  head: ({ loaderData }) =>
    loaderData
      ? head({
          title: `Evidence: ${loaderData.title} · ${book.meta.title}`,
          description: `The evidence behind Chapter ${spelled(loaderData.n)}, ${loaderData.title}.`,
          path: `/book/evidence/${loaderData.slug}`,
          ogType: "article",
          noindex: !loaderData.free,
        })
      : {},
  component: EvidenceRoute,
});

function EvidenceRoute() {
  return <BookEvidencePage evidence={Route.useLoaderData()} meta={book.meta} />;
}
