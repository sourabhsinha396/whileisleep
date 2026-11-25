import { PricingPlans } from "@/components/landing/pricing-plans";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { PRICING_QUESTIONS } from "@/lib/faq";
import { publicMetadata } from "@/lib/seo";

export const generateMetadata = () =>
  publicMetadata({
    title: "Pricing: free to self-host, or hosted",
    description: "Self-host whileisleep for free, or let us host it from $1 a month with a 14-day trial. Your AI runs on your own key, with no markup.",
    path: "/pricing",
  });

export default function PricingPage() {
  return (
    <div className="min-h-screen overflow-x-hidden">
      <SiteHeader />

      <main className="px-4 pt-8 pb-20 sm:px-6 lg:pt-14">
        <div className="mx-auto max-w-2xl text-center">
          <h1 className="text-4xl leading-[1.08] font-extrabold tracking-tight text-balance sm:text-5xl">
            Pay for the inbox, <span className="text-primary-text">not for every answer</span>
          </h1>
          <p className="mt-5 text-lg text-muted-foreground">
            Your AI runs on your own key, at your provider&apos;s price. Host it yourself for free, or let us run it.
          </p>
        </div>

        <div className="mt-12">
          <PricingPlans />
        </div>

        <section aria-labelledby="questions" className="mx-auto mt-20 max-w-2xl">
          <h2 id="questions" className="text-2xl font-bold tracking-tight">
            Questions
          </h2>
          <dl className="mt-6 divide-y border-y">
            {PRICING_QUESTIONS.map(({ q, a }) => (
              <div key={q} className="py-5">
                <dt className="font-semibold">{q}</dt>
                <dd className="mt-1.5 text-muted-foreground">{a}</dd>
              </div>
            ))}
          </dl>
        </section>
      </main>

      <SiteFooter />
    </div>
  );
}
