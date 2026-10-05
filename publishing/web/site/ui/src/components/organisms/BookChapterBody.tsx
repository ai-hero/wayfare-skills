// Copyright (c) 2026 A.I. Hero, Inc.
// All Rights Reserved.

import { Quote } from "@/components/ui/quote";
import { textVariants } from "@/components/ui/text";
import { BookFigure } from "@/components/molecules/BookFigure";
import { BookHeading } from "@/components/molecules/BookHeading";
import { BookHtml } from "@/components/molecules/BookHtml";
import type { Block, Chapter } from "@/lib/book";

export const BODY = textVariants({ variant: "body-lg" });
export const LINKS =
  "[&_a]:text-link [&_a]:underline [&_a]:underline-offset-4 [&_code]:font-mono [&_code]:text-code";

function BlockView({ block }: { block: Block }) {
  switch (block.kind) {
    case "p":
      return <BookHtml as="p" html={block.html} className={`${BODY} ${LINKS}`} />;
    case "h3":
      return <BookHeading id={block.id} html={block.html} level={3} />;
    case "quote":
      return (
        <Quote>
          <BookHtml html={block.html} />
        </Quote>
      );
    case "ul":
    case "ol": {
      const Tag = block.kind;
      return (
        <Tag
          className={`flex flex-col gap-3 ps-6 ${block.kind === "ol" ? "list-decimal" : "list-disc"} marker:text-muted-foreground ${BODY} ${LINKS}`}
        >
          {block.items.map((item, i) => (
            <BookHtml key={i} as="li" html={item} className="ps-1" />
          ))}
        </Tag>
      );
    }
    case "table":
      return (
        <BookFigure
          figure={{
            kind: "figure",
            type: "table",
            label: "",
            number: "",
            id: "",
            captionHtml: "",
            alt: "",
            rows: block.rows,
          }}
        />
      );
    case "figure":
      return <BookFigure figure={block} />;
  }
}

// A chapter's text, figures and sources: the book page and the blog posts that
// publish a chapter both render it, so the two never show different text.
export function BookChapterBody({ chapter }: { chapter: Chapter }) {
  return (
    <div className="flex flex-col gap-10">
        {chapter.sections.map((section) => (
          <section key={section.id} className="flex flex-col gap-6">
            {section.titleHtml && (
              <BookHeading id={section.id} html={section.titleHtml} level={2} />
            )}
            {section.blocks.map((block, i) => (
              <BlockView key={i} block={block} />
            ))}
          </section>
        ))}

        {chapter.sources.length > 0 && (
          <section className="flex flex-col gap-5 border-t border-hairline pt-8">
            <BookHeading id="sources" html="Sources" level={2} />
            <ol className={`flex list-decimal flex-col gap-3 ps-6 text-sm text-muted-foreground marker:font-mono marker:text-2xs ${LINKS}`}>
              {chapter.sources.map((source, i) => (
                <BookHtml key={i} as="li" html={source} className="ps-1" />
              ))}
            </ol>
          </section>
        )}
    </div>
  );
}
