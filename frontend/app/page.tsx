import { SupportWidget } from "@/components/SupportWidget";

// Every claim here matches the code: limits in backend/app/tools/actions.py, the gate in backend/app/config.py.
const FEATURES = [
  { title: "Streaming chat with live steps", body: "Each turn shows what the agent is doing (checking identity, searching policy, processing a refund) and every tool call with its input and result." },
  { title: "Live two-way voice", body: "Tap the mic to talk. Voice hands account work to the same chat agent on the same session, so it follows every rule the chat does." },
  { title: "Answers grounded in policy", body: "Retrieval over the policy documents with a similarity gate. Answers must cite the excerpts they use, and when the policy does not cover a question the agent says so instead of guessing." },
  { title: "Refunds guarded in code", body: "The model labels the request; code decides. Ownership, contract status, the 30-day window and per-tier limits ($50 Pro, $500 Enterprise per charge) are checked from records." },
  { title: "Human handoff", body: "Over-limit refunds, security or legal issues and \"talk to a person\" open a ticket with the right priority, and the customer is told what happens next." },
  { title: "Per-step cost trace", body: "Open the chart icon in the chat to see latency, tokens and cost for every step, every turn and the whole session." },
];

const DEMO_ACCOUNTS = [
  { email: "maya@example.com", last4: "4242", account: "Pro, active", tryThis: "Refund $30 on invoice in_m1, then ask for $80 more" },
  { email: "dev@example.com", last4: "1881", account: "Enterprise, active", tryThis: "Ask for a larger refund (limit $500 per charge)" },
  { email: "sam@example.com", last4: "0007", account: "Free, expired", tryThis: "Ask for a refund (not eligible)" },
  { email: "lee@example.com", last4: "5150", account: "Pro, suspended", tryThis: "Ask about your plan or a refund" },
];

export default function Home() {
  return (
    <div className="min-h-dvh">
      <header className="border-b border-line bg-surface">
        <nav className="mx-auto flex max-w-5xl items-center gap-2 px-4 py-3 text-sm sm:px-6">
          <span className="flex size-7 items-center justify-center rounded-md bg-accent text-xs font-bold text-on-accent">S</span>
          <span className="font-semibold">Customer Support AI Agent</span>
        </nav>
      </header>

      <main className="mx-auto max-w-5xl px-4 pb-32 sm:px-6">
        <section className="py-14 text-center sm:py-20">
          <p className="text-xs font-medium tracking-wide text-accent uppercase">Billing and refunds support, chat and voice</p>
          <h1 className="mx-auto mt-3 max-w-3xl text-3xl font-semibold tracking-tight sm:text-5xl">
            An AI support agent that follows the refund policy, not the conversation.
          </h1>
          <p className="mx-auto mt-4 max-w-xl text-sm text-muted sm:text-base">
            Open the chat in the corner to try it. Type a question or tap the mic to talk.
          </p>
        </section>

        <section aria-labelledby="features" className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <h2 id="features" className="sr-only">
            What it does
          </h2>
          {FEATURES.map((f) => (
            <article key={f.title} className="rounded-2xl border border-line bg-surface p-5">
              <h3 className="font-semibold">{f.title}</h3>
              <p className="mt-2 text-sm text-muted">{f.body}</p>
            </article>
          ))}
        </section>

        <section aria-labelledby="try" className="mt-14">
          <h2 id="try" className="text-lg font-semibold">
            Demo accounts
          </h2>
          <p className="mt-1 text-sm text-muted">Give the agent an email and the last 4 digits of the card to verify. All data is mock.</p>
          <div className="mt-4 overflow-x-auto rounded-2xl border border-line bg-surface">
            <table className="w-full text-left text-sm">
              <thead className="text-xs text-muted">
                <tr className="border-b border-line">
                  <th className="px-4 py-2 font-medium">Email</th>
                  <th className="px-4 py-2 font-medium">Last 4</th>
                  <th className="px-4 py-2 font-medium">Account</th>
                  <th className="px-4 py-2 font-medium">Try</th>
                </tr>
              </thead>
              <tbody>
                {DEMO_ACCOUNTS.map((a) => (
                  <tr key={a.email} className="border-b border-line last:border-0">
                    <td className="px-4 py-2 font-mono text-xs">{a.email}</td>
                    <td className="px-4 py-2 font-mono text-xs">{a.last4}</td>
                    <td className="px-4 py-2 whitespace-nowrap">{a.account}</td>
                    <td className="px-4 py-2 text-muted">{a.tryThis}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <p className="mt-12 text-center text-[11px] text-muted">
          Built with Next.js, FastAPI, Gemini (chat and Live voice) and Supabase pgvector. Runs on free tiers, so the first reply after a quiet spell can take up to a minute.
        </p>
      </main>

      <SupportWidget />
    </div>
  );
}
