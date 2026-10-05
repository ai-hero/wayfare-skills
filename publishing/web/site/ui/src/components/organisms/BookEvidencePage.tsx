// Copyright (c) 2026 A.I. Hero, Inc.
// All Rights Reserved.

import { useEffect, useState } from "react";
import { useRouter } from "@tanstack/react-router";
import { ArrowLeft, Maximize2 } from "lucide-react";
import Header from "@/components/organisms/header";
import Footer from "@/components/organisms/footer";
import { ArticleMasthead, ArticlePage } from "@/components/blocks/article-page";
import { Dialog, DialogContent, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Eyebrow } from "@/components/ui/eyebrow";
import { BookHtml } from "@/components/molecules/BookHtml";
import { BookHeading } from "@/components/molecules/BookHeading";
import { SignInPrompt } from "@/components/molecules/SignInPrompt";
import AuthModal from "@/components/organisms/AuthModal";
import { BODY, LINKS } from "@/components/organisms/BookChapterBody";
import { useAuth } from "@/hooks/useAuth";
import { spelled } from "@/lib/book";
import type {
  BookMeta,
  EvidenceBlock,
  EvidenceChapter,
  EvidenceChart,
  EvidenceContentsEntry,
  EvidenceEntry,
} from "@/lib/book";

function BackLink({ href, label }: { href: string; label: string }) {
  return (
    <a
      href={href}
      className="inline-flex items-center gap-2 rounded-sm font-mono text-2xs tracking-eyebrow text-muted-foreground uppercase transition-colors outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
    >
      <ArrowLeft aria-hidden className="size-3.5" />
      {label}
    </a>
  );
}

export function BookEvidenceIndexPage({
  meta,
  introHtml,
  chapters,
}: {
  meta: BookMeta;
  introHtml: string[];
  chapters: EvidenceContentsEntry[];
}) {
  return (
    <ArticlePage topbar={<Header />} footer={<Footer />}>
      <ArticleMasthead
        eyebrow={
          <>
            <BackLink href="/book" label={meta.title} />
            <Eyebrow>Appendix</Eyebrow>
          </>
        }
        title="Evidence"
        byline={<span className="text-sm text-foreground">{meta.author}</span>}
      />
      <div className="flex flex-col gap-5">
        {introHtml.map((html, i) => (
          <BookHtml key={i} as="p" html={html} className={`${BODY} ${LINKS}`} />
        ))}
      </div>
      <nav aria-labelledby="evidence-contents" className="flex flex-col gap-6">
        <h2 id="evidence-contents" className="text-h-1 text-foreground">
          By chapter
        </h2>
        <ol className="flex flex-col">
          {chapters.map((c) => (
            <li key={c.slug} className="border-t border-hairline py-6">
              <a
                href={`/book/evidence/${c.slug}`}
                className="group flex flex-col gap-1.5 rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <span className="flex items-baseline justify-between gap-4">
                  <Eyebrow>Chapter {spelled(c.n)}</Eyebrow>
                  <span className="font-mono text-2xs tracking-meta text-muted-foreground">
                    {c.count} {c.count === 1 ? "entry" : "entries"}
                  </span>
                </span>
                <span className="text-h-2 text-foreground transition-colors group-hover:text-link">{c.title}</span>
              </a>
            </li>
          ))}
        </ol>
      </nav>
    </ArticlePage>
  );
}

// Charts are drawn on white, so the plate stays white in dark mode.
function Chart({ chart, title }: { chart: EvidenceChart; title: string }) {
  const img = (eager?: boolean) => (
    <img
      src={chart.src}
      alt={chart.alt}
      width={chart.width}
      height={chart.height}
      loading={eager ? "eager" : "lazy"}
      decoding="async"
      className="h-auto w-full rounded-md bg-ink-white"
    />
  );
  return (
    <Dialog>
      <DialogTrigger asChild>
        <button
          type="button"
          className="group relative block cursor-zoom-in rounded-lg border border-hairline bg-ink-white p-2 outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-label={`Open the ${chart.slug} chart full size`}
        >
          {img()}
          <span className="absolute top-3 right-3 flex size-7 items-center justify-center rounded-sm border border-hairline bg-background text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100">
            <Maximize2 aria-hidden className="size-4" />
          </span>
        </button>
      </DialogTrigger>
      <DialogContent className="max-h-svh overflow-y-auto sm:max-w-7xl">
        <DialogTitle className="pr-8">{title}</DialogTitle>
        <div className="rounded-lg border border-hairline bg-ink-white p-3">{img(true)}</div>
      </DialogContent>
    </Dialog>
  );
}

function Block({ block }: { block: EvidenceBlock }) {
  switch (block.kind) {
    case "field":
      return (
        <p className={`text-base text-foreground/90 ${LINKS}`}>
          <span className="me-2 font-mono text-2xs tracking-eyebrow text-muted-foreground uppercase">
            {block.label}
          </span>
          <BookHtml html={block.html} />
        </p>
      );
    case "p":
      return <BookHtml as="p" html={block.html} className={`text-base text-foreground/90 ${LINKS}`} />;
    case "ul":
    case "ol": {
      const Tag = block.kind;
      return (
        <Tag className={`flex flex-col gap-2 ps-6 text-base ${block.kind === "ol" ? "list-decimal" : "list-disc"}`}>
          {block.items.map((item, i) => (
            <BookHtml key={i} as="li" html={item} />
          ))}
        </Tag>
      );
    }
    case "table": {
      const [head, ...body] = block.rows;
      return (
        <div className="overflow-x-auto rounded-lg border border-hairline">
          <Table>
            <TableHeader>
              <TableRow>
                {head.map((cell, i) => (
                  <TableHead key={i} className="whitespace-normal">
                    <BookHtml html={cell} />
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {body.map((row, r) => (
                <TableRow key={r}>
                  {row.map((cell, c) => (
                    <TableCell
                      key={c}
                      className={`align-top text-sm whitespace-normal ${c === 0 ? "font-mono text-xs text-muted-foreground" : "text-foreground/80"}`}
                    >
                      <BookHtml html={cell} />
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      );
    }
  }
}

function Entry({ entry }: { entry: EvidenceEntry }) {
  const title = entry.label ?? (entry.slugs.length ? entry.slugs.join(", ") : (entry.title ?? ""));
  return (
    <article id={entry.anchor} className="flex scroll-mt-24 flex-col gap-4 border-t border-hairline pt-8">
      <header className="flex flex-col gap-1.5">
        {entry.label && <Eyebrow>{entry.label}</Eyebrow>}
        <h3 className={entry.slugs.length ? "font-mono text-sm break-words text-foreground" : "text-h-2 text-foreground"}>
          <a href={`#${entry.anchor}`} className="rounded-sm outline-none hover:text-link focus-visible:ring-2 focus-visible:ring-ring">
            {entry.slugs.length ? entry.slugs.join(" · ") : entry.title}
          </a>
        </h3>
      </header>
      {entry.charts.map((chart) => (
        <Chart key={chart.slug} chart={chart} title={title} />
      ))}
      {entry.blocks.map((block, i) => (
        <Block key={i} block={block} />
      ))}
    </article>
  );
}

function Locked({ evidence }: { evidence: EvidenceChapter }) {
  const router = useRouter();
  const { isAuthenticated, refreshUser } = useAuth();
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (isAuthenticated) void router.invalidate();
  }, [isAuthenticated, router]);
  return (
    <>
      <SignInPrompt onSignIn={() => setOpen(true)} />
      <AuthModal
        isOpen={open}
        onClose={() => setOpen(false)}
        redirectUrl={`/book/evidence/${evidence.slug}`}
        onAuthSuccess={refreshUser}
      />
    </>
  );
}

export function BookEvidencePage({ evidence, meta }: { evidence: EvidenceChapter; meta: BookMeta }) {
  return (
    <ArticlePage topbar={<Header />} footer={<Footer />}>
      <ArticleMasthead
        eyebrow={
          <>
            <BackLink href="/book/evidence" label="Evidence" />
            <Eyebrow>Chapter {spelled(evidence.n)}</Eyebrow>
          </>
        }
        title={evidence.title}
        byline={<span className="text-sm text-foreground">{meta.author}</span>}
        meta={`${evidence.count} ${evidence.count === 1 ? "entry" : "entries"}`}
      />
      {evidence.locked ? (
        <Locked evidence={evidence} />
      ) : (
        <div className="flex flex-col gap-12">
          {evidence.groups.map((group) => (
            <section key={group.title} className="flex flex-col gap-8">
              <BookHeading
                id={group.title.toLowerCase().replace(/[^a-z0-9]+/g, "-")}
                html={group.title}
                level={2}
              />
              {group.entries.map((entry) => (
                <Entry key={entry.anchor} entry={entry} />
              ))}
            </section>
          ))}
        </div>
      )}
    </ArticlePage>
  );
}
