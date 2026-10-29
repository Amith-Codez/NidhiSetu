import { useQuery } from "@tanstack/react-query";
import {
  BellRing, BookOpenCheck, CalendarClock, CornerDownLeft, FileSearch, FlaskConical, Gauge, Landmark, ScrollText, Search,
  Undo2, UploadCloud, Wallet,
} from "lucide-react";
import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { api, Row } from "./api";
import { Logo } from "./ui";
import Overview from "./pages/Overview";
import Deposits from "./pages/Deposits";
import Deposit from "./pages/Deposit";
import Calendar from "./pages/Calendar";
import Alerts from "./pages/Alerts";
import Releases from "./pages/Releases";
import Verify from "./pages/Verify";
import Banks from "./pages/Banks";
import Rules from "./pages/Rules";
import Ledger from "./pages/Ledger";
import Accuracy from "./pages/Accuracy";
import Confirm from "./pages/Confirm";

type Lang = "en" | "hi";
const L = (en: string, hi: string) => ({ en, hi });
const NAV = [
  { to: "/", label: L("Overview", "अवलोकन"), icon: <Gauge size={16} />, end: true },
  { to: "/deposits", label: L("Deposit register", "जमा रजिस्टर"), icon: <Wallet size={16} /> },
  { to: "/calendar", label: L("Maturity calendar", "परिपक्वता कैलेंडर"), icon: <CalendarClock size={16} /> },
  { to: "/alerts", label: L("Alerts and escalations", "अलर्ट और एस्केलेशन"), icon: <BellRing size={16} /> },
  { to: "/releases", label: L("Release requests", "रिलीज़ अनुरोध"), icon: <Undo2 size={16} /> },
  { to: "/verify", label: L("Check an FDR", "एफडीआर जाँचें"), icon: <UploadCloud size={16} /> },
];
const NAV2 = [
  { to: "/banks", label: L("Bank channels", "बैंक चैनल"), icon: <Landmark size={16} /> },
  { to: "/rules", label: L("Rulebook", "नियम पुस्तिका"), icon: <BookOpenCheck size={16} /> },
  { to: "/ledger", label: L("Audit ledger", "ऑडिट लेजर"), icon: <ScrollText size={16} /> },
  { to: "/accuracy", label: L("Measured results", "मापे गए परिणाम"), icon: <FlaskConical size={16} /> },
];
const TITLES: Record<string, string> = {
  "": "Overview", deposits: "Deposit register", deposit: "Deposit", calendar: "Maturity calendar", alerts: "Alerts and escalations",
  releases: "Release requests", verify: "Check an FDR", banks: "Bank channels", rules: "Rulebook", ledger: "Audit ledger",
  accuracy: "Measured results", confirm: "Bank confirmation",
};
export const ROLES = [
  { id: "A. Verma (Dealing hand)", label: "Dealing hand" },
  { id: "S. Iyer (Section Officer)", label: "Section Officer" },
  { id: "Dr. R. Menon (Competent authority)", label: "Competent authority" },
];
const ZOOMS = [0.9, 1, 1.12];
export const RoleCtx = createContext<string>(ROLES[1].id);
export const useRole = () => useContext(RoleCtx);

export default function App() {
  const loc = useLocation();
  const [lang, setLang] = useState<Lang>(() => { try { return (localStorage.getItem("ns-lang") as Lang) || "en"; } catch { return "en"; } });
  const [role, setRole] = useState<string>(() => { try { return localStorage.getItem("ns-role") || ROLES[1].id; } catch { return ROLES[1].id; } });
  const [zoom, setZoom] = useState(1);
  const [palette, setPalette] = useState(false);
  const { data: health } = useQuery({ queryKey: ["health"], queryFn: () => api("/api/health"), refetchInterval: 30000 });
  const { data: rows } = useQuery({ queryKey: ["deposits", "", ""], queryFn: () => api<Row[]>("/api/instruments") });
  const { data: alerts } = useQuery({ queryKey: ["alerts"], queryFn: () => api<any[]>("/api/alerts") });
  const seg = loc.pathname.split("/")[1] || "";

  useEffect(() => { document.documentElement.style.setProperty("--zoom", String(ZOOMS[zoom])); }, [zoom]);
  useEffect(() => { try { localStorage.setItem("ns-lang", lang); localStorage.setItem("ns-role", role); } catch { /* storage may be blocked */ } }, [lang, role]);
  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setPalette((p) => !p); }
      if (e.key === "Escape") setPalette(false);
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, []);
  const counts: Record<string, number> = { "/alerts": alerts?.length || 0 };

  return (
    <RoleCtx.Provider value={role}>
      <a className="skip" href="#main">Skip to main content</a>
      <div className="govbar" role="banner">
        <span className="tri" aria-hidden="true"><i /><i /><i /></span>
        <span>Government of India</span><span className="sep full">|</span>
        <span className="full">All India Council for Technical Education · Regulation Bureau</span>
        <div className="right">
          <span className="full" style={{ opacity: .7, marginRight: 4 }}>Text size</span>
          {["A−", "A", "A+"].map((t, i) => (
            <button key={t} className={zoom === i ? "on" : ""} aria-pressed={zoom === i} aria-label={`Text size ${t}`} onClick={() => setZoom(i)}>{t}</button>
          ))}
          <span className="sep">|</span>
          <button className={lang === "en" ? "on" : ""} aria-pressed={lang === "en"} onClick={() => setLang("en")}>English</button>
          <button className={lang === "hi" ? "on" : ""} aria-pressed={lang === "hi"} onClick={() => setLang("hi")} lang="hi">हिन्दी</button>
        </div>
      </div>
      <div className="shell">
        <aside className="side" aria-label="Navigation">
          <div className="ws">
            <span className="logo"><Logo /></span>
            <div><b>NidhiSetu</b><span lang="hi">निधिसेतु · Security deposits</span></div>
          </div>
          <button className="search" onClick={() => setPalette(true)} aria-label="Search deposits and pages">
            <Search size={15} />{lang === "hi" ? "खोजें" : "Search or jump to"}<kbd>⌘K</kbd>
          </button>
          <nav className="nav">
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.end}>{n.icon}<span lang={lang}>{n.label[lang]}</span>
                {counts[n.to] ? <span className="count">{counts[n.to]}</span> : null}
              </NavLink>
            ))}
            <div className="nav-label" lang={lang}>{lang === "hi" ? "विश्वास अवसंरचना" : "Trust infrastructure"}</div>
            {NAV2.map((n) => <NavLink key={n.to} to={n.to}>{n.icon}<span lang={lang}>{n.label[lang]}</span></NavLink>)}
          </nav>
          <div className="side-foot" aria-label="System status">
            <span className="live"><span className="dot" style={health?.bank_service === "up" ? undefined : { background: "var(--exp)" }} />
              {health ? (health.bank_service === "up" ? "Bank channels online" : "Bank service unreachable") : "Connecting…"}</span>
            <span>{health?.database?.split(" ")[0] ?? "…"} · monitor runs daily · re-check every 90 days</span>
            <span>Financial data stays on AICTE servers</span>
          </div>
        </aside>
        <div className="main">
          <header className="topbar">
            <div className="crumbs">Security deposit cell <span>/</span> <b>{TITLES[seg] ?? ""}</b></div>
            <div className="spacer" />
            <span className="env">Sandbox banks · <b>synthetic data</b></span>
            <label className="role">Acting as
              <select value={role} onChange={(e) => setRole(e.target.value)} aria-label="Acting as">
                {ROLES.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
              </select>
            </label>
            <div className="who"><span className="avatar">{role.split(" ")[role.startsWith("Dr.") ? 2 : 1][0]}{role.split(" ")[0][0]}</span>{role.split(" (")[0]}</div>
          </header>
          <main id="main" tabIndex={-1}>
            <Routes>
              <Route path="/" element={<Overview />} />
              <Route path="/deposits" element={<Deposits />} />
              <Route path="/deposit/:id" element={<Deposit />} />
              <Route path="/calendar" element={<Calendar />} />
              <Route path="/alerts" element={<Alerts />} />
              <Route path="/releases" element={<Releases />} />
              <Route path="/verify" element={<Verify />} />
              <Route path="/banks" element={<Banks />} />
              <Route path="/rules" element={<Rules />} />
              <Route path="/ledger" element={<Ledger />} />
              <Route path="/accuracy" element={<Accuracy />} />
              <Route path="/confirm/:token" element={<Confirm />} />
            </Routes>
          </main>
        </div>
      </div>
      {palette && <Palette rows={rows || []} lang={lang} onClose={() => setPalette(false)} />}
    </RoleCtx.Provider>
  );
}

function Palette({ rows, lang, onClose }: { rows: Row[]; lang: Lang; onClose: () => void }) {
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const [i, setI] = useState(0);
  const items = useMemo(() => {
    const pages = [...NAV, ...NAV2].map((n) => ({ key: n.to, label: n.label[lang], hint: "Page", go: n.to, icon: n.icon }));
    const deps = rows.map((r) => ({ key: r.id, label: r.institution, hint: `${r.id} · ${r.fdr_no} · ${r.state}`, go: `/deposit/${r.id}`, icon: <FileSearch size={16} /> }));
    const all = [...pages, ...deps];
    const t = q.trim().toLowerCase();
    return t ? all.filter((x) => `${x.label} ${x.hint}`.toLowerCase().includes(t)) : all;
  }, [q, rows, lang]);
  const pick = (k: number) => { const it = items[k]; if (it) { nav(it.go); onClose(); } };
  return (
    <div className="scrim" onMouseDown={onClose} role="dialog" aria-modal="true" aria-label="Search">
      <div className="palette" onMouseDown={(e) => e.stopPropagation()}>
        <input autoFocus placeholder="Search institutions, FDR numbers or pages" value={q}
          onChange={(e) => { setQ(e.target.value); setI(0); }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") { e.preventDefault(); setI((x) => Math.min(x + 1, items.length - 1)); }
            if (e.key === "ArrowUp") { e.preventDefault(); setI((x) => Math.max(x - 1, 0)); }
            if (e.key === "Enter") pick(i);
          }} />
        <ul role="listbox">
          {items.slice(0, 12).map((it, k) => (
            <li key={it.key} role="option" aria-selected={k === i} className={k === i ? "on" : ""} onMouseEnter={() => setI(k)} onClick={() => pick(k)}>
              {it.icon}{it.label}<span className="k">{it.hint}</span>
            </li>
          ))}
          {!items.length && <li>No matches</li>}
        </ul>
        <div className="foot"><span>↑↓ to move</span><span><CornerDownLeft size={11} style={{ verticalAlign: -1 }} /> to open</span><span>Esc to close</span></div>
      </div>
    </div>
  );
}
