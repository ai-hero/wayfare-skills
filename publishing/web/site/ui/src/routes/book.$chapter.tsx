// Copyright (c) 2026 A.I. Hero, Inc.
// All Rights Reserved.

import { createFileRoute, notFound } from "@tanstack/react-router";
import { BookChapterPage } from "@/components/organisms/BookChapterPage";
import { book, getChapter, plain } from "@/lib/book";
import { head } from "@/lib/head";

// A chapter published as a blog post lives at the post's URL; its /book path
// redirects there so the same text is never indexed twice. The other chapters
// need a signed-in session (see lib/server/book.ts) and stay noindex: a crawler
// only ever sees the locked view.
export const Route = createFileRoute("/book/$chapter")({
  server: {
    handlers: {
      GET: ({ params, next }) => {
        const url = book.chapters.find((c) => c.slug === params.chapter)?.url;
        if (url) return new Response(null, { status: 308, headers: { Location: url } });
        return next();
      },
    },
  },
  loader: async ({ params }) => {
    const chapter = await getChapter({ data: params.chapter });
    if (!chapter) throw notFound();
    return chapter;
  },
  head: ({ loaderData }) => {
    if (!loaderData) return {};
    const first = loaderData.teaserHtml ?? loaderData.sections.flatMap((s) => s.blocks).flatMap((b) => (b.kind === "p" ? [b.html] : []))[0];
    const lede = first ? plain(first) : loaderData.book.title;
    return head({
      title: `${loaderData.title} · ${loaderData.book.title}`,
      description: lede.length > 160 ? `${lede.slice(0, 157).trimEnd()}…` : lede,
      path: loaderData.url ?? `/book/${loaderData.slug}`,
      ogType: "article",
      noindex: !loaderData.free,
    });
  },
  component: ChapterRoute,
});

function ChapterRoute() {
  return <BookChapterPage chapter={Route.useLoaderData()} />;
}
