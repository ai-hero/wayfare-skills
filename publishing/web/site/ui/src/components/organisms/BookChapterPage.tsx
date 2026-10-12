// Copyright (c) 2026 A.I. Hero, Inc.
// All Rights Reserved.

import { useEffect, useState } from "react";
import { useRouter } from "@tanstack/react-router";
import { ArrowLeft, ArrowRight } from "lucide-react";
import Header from "@/components/organisms/header";
import Footer from "@/components/organisms/footer";
import {
  ArticleMasthead,
  ArticlePage,
  ArticleToc,
  ArticleTocLink,
} from "@/components/blocks/article-page";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Eyebrow } from "@/components/ui/eyebrow";
import { BookHtml } from "@/components/molecules/BookHtml";
import { SignInPrompt } from "@/components/molecules/SignInPrompt";
import AuthModal from "@/components/organisms/AuthModal";
import { BookChapterBody, BODY, LINKS } from "@/components/organisms/BookChapterBody";
import { useAuth } from "@/hooks/useAuth";
import { spelled } from "@/lib/book";
import type { Chapter, ChapterLink } from "@/lib/book";


function useActiveSection(ids: string[]) {
  const [active, setActive] = useState<string | null>(null);
  useEffect(() => {
    const seen = new Map<string, boolean>();
    const observer = new IntersectionObserver(
      (entries) => {
        for (const e of entries) seen.set(e.target.id, e.isIntersecting);
        const first = ids.find((id) => seen.get(id));
        if (first) setActive(first);
      },
      { rootMargin: "-96px 0px -60% 0px" },
    );
    for (const id of ids) {
      const el = document.getElementById(id);
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
  }, [ids]);
  return active;
}

function Contents({
  chapter,
  active,
  labelled = true,
}: {
  chapter: Chapter;
  active: string | null;
  labelled?: boolean;
}) {
  return (
    <ArticleToc label={labelled ? <Eyebrow>In this chapter</Eyebrow> : undefined}>
      {chapter.sections
        .filter((s) => s.titleHtml)
        .map((s) => (
          <ArticleTocLink key={s.id} href={`#${s.id}`} active={active === s.id}>
            <BookHtml html={s.titleHtml} />
          </ArticleTocLink>
        ))}
      {chapter.sources.length > 0 && (
        <ArticleTocLink href="#sources" active={active === "sources"}>
          Sources
        </ArticleTocLink>
      )}
    </ArticleToc>
  );
}

function Neighbour({ link, dir }: { link: ChapterLink; dir: "prev" | "next" }) {
  const Icon = dir === "prev" ? ArrowLeft : ArrowRight;
  return (
    <a
      href={link.url ?? `/book/${link.slug}`}
      rel={dir}
      className={`flex flex-1 flex-col gap-2 rounded-lg border border-hairline p-5 outline-none transition-colors hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring ${dir === "next" ? "items-end text-right" : ""}`}
    >
      <span className="flex items-center gap-2 font-mono text-2xs tracking-eyebrow text-muted-foreground uppercase">
        {dir === "prev" && <Icon aria-hidden className="size-4" />}
        {dir === "prev" ? "Previous" : "Next"} · Chapter {spelled(link.n)}
        {dir === "next" && <Icon aria-hidden className="size-4" />}
      </span>
      <span className="text-lg text-foreground">{link.title}</span>
    </a>
  );
}

function LockedChapter({ chapter }: { chapter: Chapter }) {
  const router = useRouter();
  const { isAuthenticated, refreshUser } = useAuth();
  const [open, setOpen] = useState(false);
  // A session the server did not honour on this render (it arrived after the
  // page loaded): refetch, and the server decides again.
  useEffect(() => {
    if (isAuthenticated) void router.invalidate();
  }, [isAuthenticated, router]);
  return (
    <>
      {chapter.teaserHtml && (
        <div className="relative flex flex-col gap-6">
          <BookHtml as="p" html={chapter.teaserHtml} className={`${BODY} ${LINKS}`} />
          <div aria-hidden className="pointer-events-none absolute inset-x-0 bottom-0 h-16 bg-linear-to-b from-transparent to-background" />
        </div>
      )}
      <SignInPrompt onSignIn={() => setOpen(true)} />
      <nav aria-labelledby="in-this-chapter" className="flex flex-col gap-4">
        <h2 id="in-this-chapter" className="text-h-2 text-foreground">
          In this chapter
        </h2>
        <ol className="flex flex-col divide-y divide-hairline border-t border-hairline">
          {chapter.sections
            .filter((s) => s.titleHtml)
            .map((s) => (
              <BookHtml key={s.id} as="li" html={s.titleHtml} className="py-3 text-base text-foreground/80" />
            ))}
        </ol>
      </nav>
      <AuthModal
        isOpen={open}
        onClose={() => setOpen(false)}
        redirectUrl={`/book/${chapter.slug}`}
        onAuthSuccess={refreshUser}
      />
    </>
  );
}

export function BookChapterPage({ chapter }: { chapter: Chapter }) {
  if (chapter.locked) {
    return (
      <ArticlePage topbar={<Header />} footer={<Footer />}>
        <Masthead chapter={chapter} />
        <LockedChapter chapter={chapter} />
        <Neighbours chapter={chapter} />
      </ArticlePage>
    );
  }
  return <OpenChapter chapter={chapter} />;
}

function Masthead({ chapter }: { chapter: Chapter }) {
  return (
    <ArticleMasthead
      eyebrow={
        <>
          <a
            href="/book"
            className="inline-flex items-center gap-2 rounded-sm font-mono text-2xs tracking-eyebrow text-muted-foreground uppercase transition-colors outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
          >
            <ArrowLeft aria-hidden className="size-3.5" />
            {chapter.book.title}
          </a>
          <Eyebrow>Chapter {spelled(chapter.n)}</Eyebrow>
        </>
      }
      title={chapter.title}
      byline={<span className="text-sm text-foreground">{chapter.book.author}</span>}
      meta={`${chapter.minutes} min read`}
    />
  );
}

function Neighbours({ chapter }: { chapter: Chapter }) {
  return (
    <nav aria-label="Chapters" className="flex flex-col gap-4 border-t border-hairline pt-8 sm:flex-row">
      {chapter.prev ? <Neighbour link={chapter.prev} dir="prev" /> : <span className="flex-1" />}
      {chapter.next && <Neighbour link={chapter.next} dir="next" />}
    </nav>
  );
}

function OpenChapter({ chapter }: { chapter: Chapter }) {
  const ids = [
    ...chapter.sections.filter((s) => s.titleHtml).map((s) => s.id),
    ...(chapter.sources.length ? ["sources"] : []),
  ];
  const active = useActiveSection(ids);

  return (
    <ArticlePage
      topbar={<Header />}
      footer={<Footer />}
      toc={<Contents chapter={chapter} active={active} />}
    >
      <Masthead chapter={chapter} />

      <Accordion type="single" collapsible className="rounded-lg border border-hairline lg:hidden">
        <AccordionItem value="contents">
          <AccordionTrigger>In this chapter</AccordionTrigger>
          <AccordionContent className="px-5 [&_a]:no-underline">
            <Contents chapter={chapter} active={active} labelled={false} />
          </AccordionContent>
        </AccordionItem>
      </Accordion>

      <BookChapterBody chapter={chapter} />

      <Neighbours chapter={chapter} />
    </ArticlePage>
  );
}
