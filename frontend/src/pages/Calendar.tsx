import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, fmtDate, inr, Row } from "../api";
import { Days, Pill, Section } from "../ui";

export default function Calendar() {
  const { data } = useQuery({ queryKey: ["calendar"], queryFn: () => api<{ rows: Row[]; overdue: Row[] }>("/api/calendar") });
  if (!data) return <div className="page"><div className="empty">Loading…</div></div>;
  const upcoming = data.rows.filter((r) => (r.days ?? 0) >= 0);
  const byMonth: Record<string, Row[]> = {};
  upcoming.forEach((r) => { (byMonth[r.maturity_date.slice(0, 7)] ||= []).push(r); });
  const reminder = (d: number) => [90, 60, 30, 7].filter((x) => d <= x).map((x) => `${x} d`).join(", ") || "not yet";
  return (
    <div className="page">
      <div className="page-head"><div><h1>Maturity calendar</h1>
        <p>When each deposit matures, which reminders have gone out, and what is already overdue. Reminders go 90, 60, 30 and 7 days ahead.</p></div></div>
      {data.overdue.length > 0 && (
        <Section title="Overdue" sub="matured with no renewal or release request">
          <table className="table">
            <thead><tr><th>Institution</th><th>FDR</th><th className="r">Amount</th><th>Matured</th><th>Escalation</th></tr></thead>
            <tbody>{data.overdue.map((r) => (
              <tr key={r.id}><td className="inst"><Link to={`/deposit/${r.id}`}><b>{r.institution}</b></Link><span className="mono">{r.id}</span></td>
                <td className="mono small">{r.fdr_no}</td><td className="r num">{inr(r.amount)}</td><td className="small">{fmtDate(r.maturity_date)} · <Days d={r.days} /></td>
                <td className="small">{(r.days ?? 0) <= -30 ? <span className="lvl rb">Regulation Bureau</span> : (r.days ?? 0) <= -15 ? <span className="lvl ro">Regional Officer</span> : <span className="lvl due">Institution, grace period</span>}</td></tr>))}
            </tbody>
          </table>
        </Section>
      )}
      {Object.entries(byMonth).map(([m, rows]) => (
        <Section key={m} title={new Date(m + "-01T00:00:00").toLocaleDateString("en-IN", { month: "long", year: "numeric" })}
          sub={`${rows.length} deposit${rows.length > 1 ? "s" : ""} · ${inr(rows.reduce((a, r) => a + r.amount, 0), true)}`}>
          <table className="table">
            <thead><tr><th>Institution</th><th>Bank</th><th className="r">Amount</th><th>Matures</th><th>Reminders sent</th><th>Stage</th></tr></thead>
            <tbody>{rows.map((r) => (
              <tr key={r.id}><td className="inst"><Link to={`/deposit/${r.id}`}><b>{r.institution}</b></Link><span className="mono">{r.id} · {r.fdr_no}</span></td>
                <td className="small">{r.bank}</td><td className="r num">{inr(r.amount)}</td>
                <td className="small">{fmtDate(r.maturity_date)} · <Days d={r.days} /></td>
                <td className="small">{reminder(r.days ?? 999)}</td><td><Pill s={r.verification === "Discrepancy found" ? r.verification : r.state} /></td></tr>))}
            </tbody>
          </table>
        </Section>
      ))}
    </div>
  );
}
