// Copyright (c) 2026 A.I. Hero, Inc.
// All Rights Reserved.

import { Quote } from "@/components/ui/quote";
import { textVariants } from "@/components/ui/text";
import { BookFigure, BookTable } from "@/components/molecules/BookFigure";
import { BookHeading } from "@/components/molecules/BookHeading";
import { BookHtml } from "@/components/molecules/BookHtml";
import type { Block, ChapterFile, ExampleBlock, ProseBlock } from "@/lib/book";

export const BODY = textVariants({ variant: "body-lg" });
// The site maps every font-weight token to 300, so `font-semibold` is a no-op and preflight's
// `bolder` only reaches 400: a bold lead-in needs the literal weight the print book uses.
export const LINKS =
  "[&_a]:text-link [&_a]:underline [&_a]:underline-offset-4 [&_code]:font-mono [&_code]:text-code [&_strong]:[font-weight:600]";

function ExampleCard({ example }: { example: ExampleBlock }) {
  return (
    // The design system's card radius is 4px; this site's rounded-lg is 8px.
    <aside className="flex flex-col gap-2.5 rounded-sm border border-hairline p-5">
      <p className="font-mono text-2xs font-light uppercase tracking-eyebrow text-muted-foreground">{example.title}</p>
      {example.blocks.map((block, i) => (
        <ProseView key={i} block={block} />
      ))}
    </aside>
  );
}

function BlockView({ block }: { block: Block }) {
  return block.kind === "example" ? <ExampleCard example={block} /> : <ProseView block={block} />;
}

function ProseView({ block }: { block: ProseBlock }) {
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
      return <BookTable rows={block.rows} />;
    case "figure":
      return <BookFigure figure={block} />;
  }
}

// A chapter's text, figures and sources, for the book page and the blog posts.
export function BookChapterBody({ chapter }: { chapter: ChapterFile }) {
  return (
    <div className="flex flex-col gap-10">
      {chapter.sections.map((section) => (
        <section key={section.id} className="flex flex-col gap-6">
          {section.titleHtml && <BookHeading id={section.id} html={section.titleHtml} level={2} />}
          {section.blocks.map((block, i) => (
            <BlockView key={i} block={block} />
          ))}
        </section>
      ))}

      {chapter.sources.length > 0 && (
        <section className="flex flex-col gap-5 border-t border-hairline pt-8">
          <BookHeading id="sources" html="Sources" level={2} />
          <ul className={`flex flex-col gap-3 text-sm text-muted-foreground ${LINKS}`}>
            {chapter.sources.map((source) => (
              <li key={source.n} id={`ref-${source.n}`} className="flex gap-3 scroll-mt-24">
                <span className="w-8 shrink-0 font-mono text-2xs leading-5">[{source.n}]</span>
                <BookHtml html={source.html} />
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
