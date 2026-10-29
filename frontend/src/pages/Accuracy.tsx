import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { Section } from "../ui";

const SIGNAL: Record<string, string> = {
  bank_not_found: "Bank has no record", bank_differs_amount_inr: "Amount differs at bank", bank_differs_maturity_date: "Maturity differs at bank",
  bank_differs_deposit_date: "Deposit date differs", bank_differs_depositor: "Depositor differs", bank_closed_early: "Closed early at bank",
  bank_no_lien: "No lien at bank", qr_untrusted: "QR to unofficial site", pdf_overlay_edit: "White patch over text",
  field_font_mismatch: "Font differs on key field", incremental_saves: "Saved again after creation", "R-AMT-01": "Amount rule",
  "R-TEN-01": "Tenure rule", "R-DUP-01": "Already pledged", "R-FAV-01": "Not in favour of AICTE", "R-LIEN-01": "No lien on receipt",
  "R-IFSC-01": "Unknown branch", "R-MAT-01": "Maturity arithmetic", post_issue_edit: "Edited after issue",
};

export default function Accuracy() {
  const { data: ev } = useQuery({ queryKey: ["eval"], queryFn: () => api("/api/eval") });
  if (!ev?.groups) return <div className="page"><div className="empty">No measurement yet. Run scripts/evaluate.py.</div></div>;
  const sim = ev.closure_simulation;
  return (
    <div className="page">
      <div className="page-head"><div><h1>Measured results</h1>
        <p>{ev.documents} labelled receipts from our test harness: {ev.genuine} genuine ({ev.groups.find((g: any) => g.group === "genuine_photo")?.n} of them phone photos) and {ev.forged} forged, across 8 forgery patterns taken from reported cases. Synthetic data from sandbox banks; real-world rates are measured in the pilot.</p></div></div>
      <div className="stats">
        <div className="stat"><span className="label">Forgeries caught</span><span className="value" style={{ color: "var(--ok)" }}>{ev.caught}<small>/ {ev.forged}</small></span><span className="foot">{ev.multi_signal_types} of 8 patterns caught by 2+ independent signals</span></div>
        <div className="stat"><span className="label">False alarms on genuine receipts</span><span className="value">{ev.false_alarms}<small>/ {ev.genuine}</small></span><span className="foot">genuine receipts the bank confirmed</span></div>
        <div className="stat"><span className="label">Median time per receipt</span><span className="value">{(ev.median_ms_pdf / 1000).toFixed(2)}<small>s</small></span><span className="foot">PDF; {(ev.median_ms_photo / 1000).toFixed(1)} s for a phone photo (OCR)</span></div>
        <div className="stat alert"><span className="label">Early closure found after</span><span className="value">{sim.ours_median_days}<small>days</small></span><span className="foot">median, vs {sim.paper_median_days} days when checked only at maturity</span></div>
      </div>
      <table className="table">
        <thead><tr><th>Test group</th><th>Result</th><th>Signals that fired (receipts)</th><th className="r">Median</th></tr></thead>
        <tbody>{ev.groups.map((g: any) => (
          <tr key={g.group}>
            <td>{g.label}</td>
            <td><span className={`st ${g.ok === g.n ? "s-ok" : "s-rev"}`}>{g.ok} of {g.n} {g.metric}</span></td>
            <td className="small">{Object.entries(g.signals).map(([k, n]) => <span key={k} className="tag">{SIGNAL[k] || k} ({String(n)})</span>)}
              {!Object.keys(g.signals).length && <span className="muted">none, correctly</span>}</td>
            <td className="r num">{g.median_ms} ms</td>
          </tr>))}
        </tbody>
      </table>
      <Section title="Early closure: when is it found?" sub="simulation">
        <p style={{ margin: 0, color: "var(--n-700)", maxWidth: "80ch" }}>
          {sim.deposits.toLocaleString("en-IN")} simulated deposits of 5 to 8 years, each closed early at a random time. Checked only on paper, the closure surfaces when the deposit is due:
          after a median {sim.paper_median_days.toLocaleString("en-IN")} days (90th percentile {sim.paper_p90_days.toLocaleString("en-IN")}). With the bank re-asked every {sim.recheck_days} days,
          it surfaces in a median {sim.ours_median_days} days and never later than {sim.ours_max_days}. In the 2026 Panchkula case the missing ₹150 crore of FDs came to light only on a maturity transfer request.</p>
      </Section>
    </div>
  );
}
