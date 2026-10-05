// Copyright (c) 2026 A.I. Hero, Inc.
// All Rights Reserved.

import { ArrowRight, Maximize2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Eyebrow } from "@/components/ui/eyebrow";
import { BookHtml } from "@/components/molecules/BookHtml";
import type { FigureBlock } from "@/lib/book";

function Caption({ figure }: { figure: FigureBlock }) {
  return (
    <figcaption className="flex flex-col gap-1.5">
      <Eyebrow>
        {figure.label} {figure.number}
      </Eyebrow>
      <BookHtml
        as="p"
        html={figure.captionHtml}
        className="text-sm text-muted-foreground"
      />
      {figure.evidence && (
        <a
          href={figure.evidence}
          className="inline-flex w-fit items-center gap-1.5 rounded-sm font-mono text-2xs tracking-eyebrow text-link uppercase outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring"
        >
          Evidence
          <ArrowRight aria-hidden className="size-3.5" />
        </a>
      )}
    </figcaption>
  );
}

// Every figure is drawn on white, so its plate stays white in dark mode
// (`bg-ink-white` is constant across themes); on the page ground it would be
// dark ink on dark ink.
function Picture({ figure, full }: { figure: FigureBlock; full?: boolean }) {
  return (
    <img
      src={figure.src}
      alt={figure.alt}
      width={figure.width}
      height={figure.height}
      loading={full ? "eager" : "lazy"}
      decoding="async"
      className="h-auto w-full rounded-md bg-ink-white"
    />
  );
}

// A wide reference table (the manuscript's has seven text columns) cannot be
// read inside the prose measure, so the page shows it as one block per row and
// the real grid opens full width on demand. A row with only its first cell is
// a group heading ("Control plane", "Work cell").
function BookTable({ figure, rows }: { figure: FigureBlock; rows: string[][] }) {
  const [head, ...body] = rows;
  const title = `${figure.label} ${figure.number}`.trim();
  return (
    <figure id={figure.id || undefined} className="flex scroll-mt-24 flex-col gap-3">
      <div className="flex flex-col rounded-lg border border-hairline">
        {body.map((row, r) =>
          row.slice(1).every((c) => !c) ? (
            <div key={r} className="border-b border-hairline bg-muted px-5 py-2.5 last:border-b-0">
              <Eyebrow>
                <BookHtml html={row[0]} />
              </Eyebrow>
            </div>
          ) : (
            <dl key={r} className="grid gap-x-6 gap-y-3 border-b border-hairline px-5 py-4 last:border-b-0 sm:grid-cols-2">
              <BookHtml as="dt" html={row[0]} className="text-base text-foreground sm:col-span-2" />
              {row.slice(1).map((cell, c) =>
                cell ? (
                  <div key={c} className="flex flex-col gap-1">
                    <dt>
                      <Eyebrow>
                        <BookHtml html={head[c + 1]} />
                      </Eyebrow>
                    </dt>
                    <BookHtml as="dd" html={cell} className="text-sm text-foreground/80" />
                  </div>
                ) : null,
              )}
            </dl>
          ),
        )}
      </div>
      {figure.captionHtml && <Caption figure={figure} />}
      <Dialog>
        <DialogTrigger asChild>
          <Button variant="outline" size="sm" className="w-fit">
            <Maximize2 aria-hidden />
            Open as a table
          </Button>
        </DialogTrigger>
        <DialogContent className="max-h-svh overflow-y-auto sm:max-w-7xl">
          <DialogTitle className="pr-8">{title || "Table"}</DialogTitle>
          {figure.captionHtml && (
            <DialogDescription>
              <BookHtml html={figure.captionHtml} />
            </DialogDescription>
          )}
          <Table className="min-w-5xl">
            <TableHeader>
              <TableRow>
                {head.map((cell, i) => (
                  <TableHead key={i} className="align-bottom whitespace-normal">
                    <BookHtml html={cell} />
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {body.map((row, r) => (
                <TableRow key={r}>
                  {row.map((cell, c) => (
                    <TableCell key={c} className="align-top text-xs whitespace-normal text-foreground/80">
                      <BookHtml html={cell} />
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </DialogContent>
      </Dialog>
    </figure>
  );
}

export function BookFigure({ figure }: { figure: FigureBlock }) {
  if (figure.type === "table" && figure.rows) {
    return <BookTable figure={figure} rows={figure.rows} />;
  }

  if (!figure.src) {
    return (
      <figure id={figure.id} className="flex flex-col gap-3">
        <Caption figure={figure} />
      </figure>
    );
  }

  return (
    <figure id={figure.id} className="flex scroll-mt-24 flex-col gap-3">
      <Dialog>
        <DialogTrigger asChild>
          <button
            type="button"
            className="group relative block cursor-zoom-in rounded-lg border border-hairline bg-ink-white p-2 outline-none focus-visible:ring-2 focus-visible:ring-ring"
            aria-label={`Open ${figure.label} ${figure.number} full size`}
          >
            <Picture figure={figure} />
            <span className="absolute top-3 right-3 flex size-7 items-center justify-center rounded-sm border border-hairline bg-background text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100">
              <Maximize2 aria-hidden className="size-4" />
            </span>
          </button>
        </DialogTrigger>
        <DialogContent className="max-h-svh overflow-y-auto sm:max-w-7xl">
          <DialogTitle className="pr-8">
            {figure.label} {figure.number}
          </DialogTitle>
          <DialogDescription>
            <BookHtml html={figure.captionHtml} />
          </DialogDescription>
          <div className="rounded-lg border border-hairline bg-ink-white p-3">
            <Picture figure={figure} full />
          </div>
        </DialogContent>
      </Dialog>
      <Caption figure={figure} />
    </figure>
  );
}
