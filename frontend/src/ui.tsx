import { ListChecks, ScanSearch, ScanText, ShieldCheck, Scale } from "lucide-react";
import type { ReactNode } from "react";

const TONE: Record<string, string> = {
  "Active": "s-ok", "Expiring": "s-exp", "Matured": "s-bad", "Renewed": "s-na", "Release in progress": "s-pend",
  "Released": "s-na", "Pending verification": "s-pend",
  "Confirmed by bank": "s-ok", "Declared, awaiting bank": "s-pend", "Discrepancy found": "s-bad",
};

/** Plain-language meaning of each state, shown on hover and in the registry's legend. */
export const HELP: Record<string, string> = {
  "Active": "In force, more than 90 days to maturity, confirmed by the bank.",
  "Expiring": "Matures within 90 days. The institution has been reminded to renew.",
  "Matured": "Past maturity with no renewal or release request. Escalates after 15 and 30 days.",
  "Renewed": "Replaced by a newer FDR that the bank has confirmed.",
  "Release in progress": "A release or refund request is moving through scrutiny and approval.",
  "Released": "Released by the competent authority; the bank was asked to remove AICTE's lien.",
  "Pending verification": "Declared by the institution; waiting for the bank to confirm.",
  "Confirmed by bank": "The bank itself confirmed the amount, dates, lien and status.",
  "Declared, awaiting bank": "Only the institution's word so far. The bank has been asked.",
  "Discrepancy found": "The bank's record and the receipt disagree, or a rule failed. Open the evidence.",
};

export const tone = (s: string) => TONE[s] || "s-q";

export function Pill({ s, lg = false }: { s: string; lg?: boolean }) {
  return <span className={`st ${tone(s)} ${lg ? "lg" : ""}`} title={HELP[s]}>{s}</span>;
}

export function Logo({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" fill="none" stroke="#fff" strokeWidth="2.4" strokeLinejoin="round" strokeLinecap="round">
      <path d="M16 6l10 5H6z" />
      <path d="M9 14v7M14 14v7M18 14v7M23 14v7M6 24h20" />
      <circle cx="26" cy="6" r="3" fill="#E89C30" stroke="#4A2BC2" strokeWidth="1.2" />
    </svg>
  );
}

export const ENGINE: Record<string, { label: string; icon: ReactNode; blurb: string }> = {
  READ: { label: "Read", icon: <ScanText size={14} />, blurb: "Fields off the receipt" },
  CHECK: { label: "Check", icon: <ListChecks size={14} />, blurb: "Security deposit rules" },
  CONFIRM: { label: "Confirm", icon: <ShieldCheck size={14} />, blurb: "Ask the bank" },
  DETECT: { label: "Detect", icon: <ScanSearch size={14} />, blurb: "Tampering signs" },
  DECIDE: { label: "Decide", icon: <Scale size={14} />, blurb: "Status and risk" },
};

export function Section({ title, sub, right, children }: { title?: string; sub?: string; right?: ReactNode; children: ReactNode }) {
  return (
    <section className="section">
      {title && <div className="section-h"><h2>{title}</h2>{sub && <span className="sub">{sub}</span>}{right && <div className="right">{right}</div>}</div>}
      {children}
    </section>
  );
}

export const OUTCOME_ICON = (o: string, sev?: string) =>
  o === "Confirmed by bank" ? "i-ok" : o === "Discrepancy found" ? "i-bad" : o === "flag" ? "i-rev" :
    o === "Declared, awaiting bank" ? (sev === "info" ? "i-pend" : "i-pend") : "i-info";

export function Days({ d }: { d: number | null }) {
  if (d == null) return <span className="muted">–</span>;
  const c = d < 0 ? "var(--bad)" : d <= 30 ? "var(--exp)" : d <= 90 ? "var(--rev)" : "var(--n-600)";
  return <span className="num" style={{ color: c }}>{d < 0 ? `${-d} d overdue` : `${d} d`}</span>;
}
