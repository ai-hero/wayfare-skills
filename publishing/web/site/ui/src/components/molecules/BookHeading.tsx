// Copyright (c) 2026 A.I. Hero, Inc.
// All Rights Reserved.

import { useState } from "react";
import { Check, Link as LinkIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { BookHtml } from "@/components/molecules/BookHtml";

// Plain strings, not cn(): tailwind-merge reads `text-h-1` as a colour and
// drops it in favour of `text-foreground`, leaving headings at body size.
const LEVEL = {
  2: "text-h-1 text-balance text-foreground",
  3: "text-h-2 text-balance text-foreground",
} as const;

// A section heading that is also its own permalink: the anchor button copies
// the full URL, so a reader can cite a section without hunting for the id.
export function BookHeading({
  id,
  html,
  level,
}: {
  id: string;
  html: string;
  level: 2 | 3;
}) {
  const [copied, setCopied] = useState(false);
  const Tag = level === 2 ? "h2" : "h3";

  async function copy() {
    const url = `${window.location.origin}${window.location.pathname}#${id}`;
    window.history.replaceState(null, "", `#${id}`);
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div className="group flex scroll-mt-24 items-start gap-2" id={id}>
      <BookHtml as={Tag} html={html} className={LEVEL[level]} />
      <Button
        variant="ghost"
        size="icon-xs"
        onClick={copy}
        aria-label={copied ? "Link copied" : "Copy link to this section"}
        className="mt-1 opacity-100 transition-opacity group-hover:opacity-100 focus-visible:opacity-100 lg:opacity-0"
      >
        {copied ? <Check aria-hidden /> : <LinkIcon aria-hidden />}
      </Button>
    </div>
  );
}
