// Copyright (c) 2026 A.I. Hero, Inc.
// All Rights Reserved.

import type { ElementType } from "react";

// The edition's inline Markdown, rendered and sanitized at build time by
// `./publish web` (inline marks only: a, em, strong, code, br). Not routed
// through DOMPurify on purpose: its server half pulls jsdom into SSR, which
// the production bundle cannot load. Only ever pass it `src/data/book` text.
export function BookHtml({
  html,
  as: Tag = "span",
  className,
  id,
}: {
  html: string;
  as?: ElementType;
  className?: string;
  id?: string;
}) {
  return <Tag id={id} className={className} dangerouslySetInnerHTML={{ __html: html }} />;
}
