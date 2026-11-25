import { SupportWidget } from "@/components/SupportWidget";

// Plan features mirror backend/data/policies/plans.md so the page never contradicts the agent. No prices: the policies have none.
const PLANS = [
  { name: "Free", blurb: "For trying things out", features: ["One workspace", "3 projects", "Community forum support"] },
  { name: "Pro", blurb: "For growing teams", features: ["Unlimited projects", "10 seats, add more any time", "Live chat support, 4 business hour target", "Monthly billing"], isFeatured: true },
  { name: "Enterprise", blurb: "For organisations", features: ["SSO and audit logs", "Dedicated account manager", "24/7 support, 1 hour target on high priority", "Annual contracts"] },
];

export default function Home() {
  return (
    <div className="min-h-dvh">
      <header className="border-b border-line bg-surface">
        <nav className="mx-auto flex max-w-5xl items-center gap-6 px-4 py-3 text-sm sm:px-6">
          <span className="flex items-center gap-2 font-semibold">
            <span className="flex size-7 items-center justify-center rounded-md bg-accent text-xs font-bold text-on-accent">A</span>
            Acme Projects
          </span>
          <span className="hidden text-muted sm:inline">Product</span>
          <span className="hidden text-muted sm:inline">Pricing</span>
          <span className="hidden text-muted sm:inline">Docs</span>
          <span className="ml-auto rounded-lg border border-line px-3 py-1.5 text-xs">Sign in</span>
        </nav>
      </header>

      <main className="mx-auto max-w-5xl px-4 pb-32 sm:px-6">
        <section className="py-16 text-center sm:py-24">
          <p className="text-xs font-medium tracking-wide text-accent uppercase">Project planning for small teams</p>
          <h1 className="mx-auto mt-3 max-w-2xl text-3xl font-semibold tracking-tight sm:text-5xl">Plan, track and ship work in one place.</h1>
          <p className="mx-auto mt-4 max-w-xl text-sm text-muted sm:text-base">
            Questions about billing, refunds or your plan? Open the chat in the corner. Type, or tap the mic to talk.
          </p>
        </section>

        <section aria-labelledby="plans" className="grid gap-4 sm:grid-cols-3">
          <h2 id="plans" className="sr-only">
            Plans
          </h2>
          {PLANS.map((plan) => (
            <article
              key={plan.name}
              className={`rounded-2xl border bg-surface p-5 ${plan.isFeatured ? "border-accent shadow-lg" : "border-line"}`}
            >
              <h3 className="font-semibold">{plan.name}</h3>
              <p className="text-xs text-muted">{plan.blurb}</p>
              <ul className="mt-4 space-y-2 text-sm">
                {plan.features.map((f) => (
                  <li key={f} className="flex gap-2">
                    <span aria-hidden className="text-ok">
                      ✓
                    </span>
                    {f}
                  </li>
                ))}
              </ul>
            </article>
          ))}
        </section>

        <p className="mt-12 text-center text-[11px] text-muted">
          Demo site for a customer support agent. Acme Projects is fictional; accounts and charges are mock data.
        </p>
      </main>

      <SupportWidget />
    </div>
  );
}
