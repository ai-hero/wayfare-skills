// Copyright (c) 2026 A.I. Hero, Inc.
// All Rights Reserved.

import { createFileRoute } from "@tanstack/react-router";
import { BookContentsPage } from "@/components/organisms/BookContentsPage";
import { book } from "@/lib/book";
import { head } from "@/lib/head";

// Public and indexable: the full contents is the pitch for the email wall.
export const Route = createFileRoute("/book/")({
  head: () =>
    head({
      title: book.meta.title,
      description: book.meta.subtitle || book.meta.title,
      path: "/book",
      ogType: "website",
    }),
  component: () => <BookContentsPage meta={book.meta} chapters={book.chapters} />,
});
