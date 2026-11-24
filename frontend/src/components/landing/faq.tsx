import { Plus } from "lucide-react";
import { HOME_QUESTIONS } from "@/lib/faq";

/** Native `details`: opens without JavaScript and brings its own keyboard behaviour. */
export function Faq() {
  return (
    <section id="faq" aria-labelledby="faq-title" className="mx-auto max-w-3xl scroll-mt-6 px-4 py-16 sm:px-6">
      <h2 id="faq-title" className="text-center text-3xl font-bold tracking-tight sm:text-4xl">
        Frequently asked questions
      </h2>
      <div className="mt-10 divide-y border-y">
        {HOME_QUESTIONS.map(({ q, a }) => (
          <details key={q} className="group">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-4 py-5 font-semibold [&::-webkit-details-marker]:hidden">
              {q}
              <Plus size={18} aria-hidden className="shrink-0 text-primary-text transition-transform group-open:rotate-45" />
            </summary>
            <p className="pb-5 text-muted-foreground">{a}</p>
          </details>
        ))}
      </div>
    </section>
  );
}
