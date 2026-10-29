import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, fmtDate, inr, post } from "../api";
import { Section } from "../ui";

const LADDER = [
  ["Reminder", "90, 60, 30 and 7 days before maturity", "Institution · email and SMS"],
  ["Action due", "On maturity, if no renewal or release request", "Institution, 15-day grace"],
  ["Escalated to Regional Officer", "15 days overdue, or bank past its SLA", "Regional Officer"],
  ["Escalated to Regulation Bureau", "30 days overdue, or any discrepancy", "Regulation Bureau"],
];
const cls = (l: string) => (l.includes("Bureau") ? "rb" : l.includes("Regional") ? "ro" : l === "Action due" ? "due" : "");

export default function Alerts() {
  const qc = useQueryClient();
  const [tab, setTab] = useState<"open" | "sent">("open");
  const { data: alerts } = useQuery({ queryKey: ["alerts"], queryFn: () => api<any[]>("/api/alerts") });
  const { data: sent } = useQuery({ queryKey: ["notifications"], queryFn: () => api<any[]>("/api/notifications") });
  async function ack(id: number) { await post(`/api/alerts/${id}/ack`); qc.invalidateQueries({ queryKey: ["alerts"] }); }
  return (
    <div className="page">
      <div className="page-head"><div><h1>Alerts and escalations</h1>
        <p>Nobody has to remember a date. The monitor raises each alert once, sends it, and moves it up the ladder if nothing happens.</p></div></div>
      <div className="stats">
        {LADDER.map(([l, when, who]) => (
          <div key={l} className="stat"><span className="label"><span className={`lvl ${cls(l)}`}>{l}</span></span>
            <span className="value">{(alerts || []).filter((a) => a.level === l).length}</span><span className="foot">{when} · {who}</span></div>
        ))}
      </div>
      <div className="tabs" role="tablist">
        <button role="tab" aria-selected={tab === "open"} className={tab === "open" ? "on" : ""} onClick={() => setTab("open")}>Open alerts ({alerts?.length ?? 0})</button>
        <button role="tab" aria-selected={tab === "sent"} className={tab === "sent" ? "on" : ""} onClick={() => setTab("sent")}>Notifications sent</button>
      </div>
      {tab === "open" ? (
        <Section>
          <div className="feed">
            {alerts?.map((a) => (
              <div key={a.id} className="ev" style={{ gridTemplateColumns: "minmax(0,1fr) auto auto", alignItems: "center" }}>
                <span><span className={`lvl ${cls(a.level)}`}>{a.level}</span> <b style={{ fontWeight: 500 }}>{a.title}</b>
                  <div className="small muted"><Link to={`/deposit/${a.instrument_id}`}>{a.inst_name}</Link> · {a.instrument_id} · {inr(a.amount)} · {a.detail}</div></span>
                <span className="h">{fmtDate(a.created_at)}</span>
                <button className="btn ghost" onClick={() => ack(a.id)} aria-label={`Acknowledge alert ${a.id}`}><Check size={14} />Acknowledge</button>
              </div>
            ))}
            {alerts && !alerts.length && <div className="empty">No open alerts. Every deposit is in order.</div>}
          </div>
        </Section>
      ) : (
        <table className="table">
          <thead><tr><th>Sent</th><th>Channel</th><th>To</th><th>Subject</th><th>Level</th></tr></thead>
          <tbody>{sent?.map((n) => (
            <tr key={n.id}><td className="small mono">{n.sent_at.replace("T", " ").slice(0, 16)}</td><td className="small">{n.channel}</td>
              <td className="small mono">{n.recipient}</td><td className="small">{n.subject} · <Link to={`/deposit/${n.instrument_id}`}>{n.instrument_id}</Link></td>
              <td><span className={`lvl ${cls(n.level || "")}`}>{n.level}</span></td></tr>))}
          </tbody>
        </table>
      )}
    </div>
  );
}
