import { useQuery } from "@tanstack/react-query";
import { Check, Minus } from "lucide-react";
import { api } from "../api";

export default function Banks() {
  const { data } = useQuery({ queryKey: ["banks"], queryFn: () => api<any[]>("/api/banks") });
  const yes = (b: boolean) => (b ? <Check size={16} color="var(--ok)" aria-label="Yes" /> : <Minus size={16} color="var(--n-500)" aria-label="No" />);
  return (
    <div className="page">
      <div className="page-head"><div><h1>Bank channels</h1>
        <p>How each bank confirms a deposit, strongest channel first. Only AICTE administrators edit this list. Phone numbers, emails or QR links printed on a receipt are never used.</p></div></div>
      <div className="stats">
        <div className="stat"><span className="label">Tier 1 · instant</span><span className="foot" style={{ fontSize: 13, color: "var(--n-700)" }}>e-FDR signed by the bank, checked against its registered certificate; or a QR code that opens the bank's allow-listed domain.</span></div>
        <div className="stat"><span className="label">Tier 2 · seconds</span><span className="foot" style={{ fontSize: 13, color: "var(--n-700)" }}>The bank's term-deposit API returns amount, dates, AICTE's lien and status. Re-asked every 90 days.</span></div>
        <div className="stat"><span className="label">Tier 3 · days</span><span className="foot" style={{ fontSize: 13, color: "var(--n-700)" }}>A signed one-time "Did your branch issue this?" link to the branch contact held here. No answer by the SLA escalates.</span></div>
        <div className="stat"><span className="label">Next · with consent</span><span className="foot" style={{ fontSize: 13, color: "var(--n-700)" }}>RBI's Account Aggregator framework already lists term deposits as a data type; the institution would consent once.</span></div>
      </div>
      <table className="table">
        <thead><tr><th>Bank</th><th>Signed e-FDR</th><th>QR domain</th><th>API</th><th>Branch contact (Tier 3)</th><th className="r">SLA</th><th>AA ready</th><th className="r">Deposits</th><th className="r">Confirmed</th></tr></thead>
        <tbody>{data?.map((b) => (
          <tr key={b.code}>
            <td className="inst"><b>{b.name}</b><span className="mono">{b.code} · {b.branches.length} branches · sandbox</span></td>
            <td>{yes(b.signed_efdr)}</td><td className="mono small">{b.qr_domains.join(", ") || "–"}</td><td>{yes(b.api)}</td>
            <td className="mono small">{b.contact}</td><td className="r num">{b.sla_days} days</td><td>{yes(b.aa)}</td>
            <td className="r num">{b.deposits}</td><td className="r num">{b.confirmed}</td>
          </tr>))}
        </tbody>
      </table>
      <p className="small muted" style={{ margin: 0 }}>IFSC codes are checked against a branch list that stands in for RBI's NEFT/RTGS IFSC list; in production that list is refreshed monthly.</p>
    </div>
  );
}
