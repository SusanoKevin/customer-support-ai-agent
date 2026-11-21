import type { Escalation } from "@/lib/conversation";
import { humanize } from "@/lib/format";

export function EscalationBanner({ escalation }: { escalation: Escalation }) {
  return (
    <div role="status" className="rounded-lg border border-warn/40 bg-warn/10 px-3 py-2 text-xs">
      <div className="font-semibold text-warn">Handed off to a person</div>
      <div className="mt-0.5 text-muted">
        Reason: {humanize(escalation.reason)}
        {escalation.ticket_id && (
          <>
            {" · Ticket "}
            <span className="font-mono">{escalation.ticket_id}</span>
          </>
        )}
        {escalation.priority && ` · ${humanize(escalation.priority)} priority`}
      </div>
    </div>
  );
}
