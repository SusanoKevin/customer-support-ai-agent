import { totals, type Totals, type Turn } from "@/lib/conversation";
import { formatMs, formatUsd, humanize } from "@/lib/format";

interface TraceDrawerProps {
  turns: Turn[];
  session: Totals;
  sessionId: string;
}

export function TraceDrawer({ turns, session, sessionId }: TraceDrawerProps) {
  return (
    <section aria-label="Observability" className="flex h-full flex-col">
      <header className="border-b border-line px-4 py-3">
        <h2 className="text-sm font-semibold">Observability</h2>
        <p className="font-mono text-[11px] text-muted">{sessionId}</p>
        <dl className="mt-3 grid grid-cols-3 gap-2 text-center">
          <Stat label="Latency" value={formatMs(session.latencyMs)} />
          <Stat label="Tokens" value={(session.tokensIn + session.tokensOut).toLocaleString()} />
          <Stat label="Cost" value={formatUsd(session.costUsd)} />
        </dl>
      </header>
      <div className="flex-1 space-y-4 overflow-y-auto px-4 py-3">
        {turns.length === 0 && <p className="text-xs text-muted">Send a message to see each step.</p>}
        {[...turns].reverse().map((turn) => (
          <TurnTable key={turn.id} turn={turn} />
        ))}
      </div>
      <footer className="border-t border-line px-4 py-2 text-[11px] leading-snug text-muted">
        Cost is the paid-tier list price per call. This demo runs on the free tier.
      </footer>
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-surface-2 px-2 py-1.5">
      <dt className="text-[10px] uppercase tracking-wide text-muted">{label}</dt>
      <dd className="font-mono text-sm tabular-nums">{value}</dd>
    </div>
  );
}

function TurnTable({ turn }: { turn: Turn }) {
  const sum = totals(turn.rows);
  return (
    <div>
      <p className="mb-1 truncate text-xs font-medium" title={turn.prompt}>
        “{turn.prompt}”
      </p>
      <table className="w-full font-mono text-[11px] tabular-nums">
        <thead className="text-left text-muted">
          <tr>
            <th className="py-1 font-normal">Step</th>
            <th className="py-1 text-right font-normal">Time</th>
            <th className="py-1 text-right font-normal">In/Out</th>
            <th className="py-1 text-right font-normal">Cost</th>
          </tr>
        </thead>
        <tbody>
          {turn.rows.map((r, i) => (
            <tr key={`${r.step}-${i}`} className="border-t border-line align-top">
              <td className="py-1">
                {humanize(r.step)}
                {r.model && <div className="text-[10px] text-muted">{r.model}</div>}
              </td>
              <td className="py-1 text-right">{formatMs(r.latencyMs)}</td>
              <td className="py-1 text-right">{r.model ? `${r.tokensIn}/${r.tokensOut}` : "-"}</td>
              <td className="py-1 text-right">{r.model ? formatUsd(r.costUsd) : "-"}</td>
            </tr>
          ))}
          <tr className="border-t border-line font-semibold">
            <td className="py-1">Turn total</td>
            <td className="py-1 text-right">{formatMs(sum.latencyMs)}</td>
            <td className="py-1 text-right">{`${sum.tokensIn}/${sum.tokensOut}`}</td>
            <td className="py-1 text-right">{formatUsd(sum.costUsd)}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}
