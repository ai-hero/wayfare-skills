// Copyright (c) 2026 A.I. Hero, Inc.
// All Rights Reserved.

import Header from "@/components/organisms/header";
import Footer from "@/components/organisms/footer";
import {
  ArticleMasthead,
  ArticlePage,
} from "@/components/blocks/article-page";
import { Eyebrow } from "@/components/ui/eyebrow";
import { Badge } from "@/components/ui/badge";
import { spelled } from "@/lib/book";
import type { BookMeta, ContentsEntry } from "@/lib/book";

export function BookContentsPage({
  meta,
  chapters,
}: {
  meta: BookMeta;
  chapters: ContentsEntry[];
}) {
  return (
    <ArticlePage topbar={<Header />} footer={<Footer />}>
      <ArticleMasthead
        className="[&_h1]:font-serif"
        eyebrow={<Eyebrow>{meta.edition ? `${meta.edition} edition` : "Book"}</Eyebrow>}
        title={meta.title}
        lede={meta.subtitle || undefined}
        byline={
          <span className="text-sm text-foreground">
            {meta.author}
            {meta.affiliation && <span className="text-muted-foreground"> · {meta.affiliation}</span>}
          </span>
        }
        meta={meta.date}
      />

      <nav aria-labelledby="contents" className="flex flex-col gap-6">
        <h2 id="contents" className="text-h-1 text-foreground">
          Contents
        </h2>
        <ol className="flex flex-col">
          {chapters.map((c) => (
            <li key={c.slug} className="border-t border-hairline py-6">
              <a
                href={c.url ?? `/book/${c.slug}`}
                className="group flex flex-col gap-1.5 rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <span className="flex items-baseline justify-between gap-4">
                  <span className="flex items-center gap-3">
                    <Eyebrow>Chapter {spelled(c.n)}</Eyebrow>
                    {c.free && <Badge variant="secondary">Free</Badge>}
                  </span>
                  <span className="font-mono text-2xs tracking-meta text-muted-foreground">
                    {c.minutes} min
                  </span>
                </span>
                <span className="text-h-2 text-foreground transition-colors group-hover:text-link">
                  {c.title}
                </span>
              </a>
            </li>
          ))}
          <li className="border-t border-hairline py-6">
            <a
              href="/book/evidence"
              className="group flex flex-col gap-1.5 rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <Eyebrow>Appendix</Eyebrow>
              <span className="text-h-2 text-foreground transition-colors group-hover:text-link">Evidence</span>
            </a>
          </li>
        </ol>
      </nav>
    </ArticlePage>
  );
}
