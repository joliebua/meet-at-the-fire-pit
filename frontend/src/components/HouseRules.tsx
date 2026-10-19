import { useEffect, useState } from "react";
import { api, fmtUsd, type League, type Rule } from "../api";
import { ErrorBox, EVENT_ICONS, ImpactTable, Loading, Points } from "./common";

type Props = { leagueKey: string; league: League; onChanged: (msg?: string) => void };
type Proposal = Awaited<ReturnType<typeof api.proposeRules>>;

const EXAMPLE = "Steals are worth 5 extra points. Winning a challenge should be worth 8. Anyone who cries at the fire pit loses 2.";

function describe(r: Rule) {
  const bits = [];
  if (r.quote_keywords.length) bits.push(`when the recap says ${r.quote_keywords.map((k) => `“${k}”`).join(" / ")}`);
  if (r.min_day || r.max_day) bits.push(`days ${r.min_day ?? 1}–${r.max_day ?? "end"}`);
  if (r.replaces) bits.push(`replaces ${r.replaces}`);
  if (r.applies_to !== "islanders") bits.push(`applies to ${r.applies_to}`);
  return bits.join(" · ");
}

export default function HouseRules({ leagueKey, league, onChanged }: Props) {
  const [rules, setRules] = useState<Rule[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.standings(leagueKey).then((s) => setRules(s.rules.filter((r) => r.source === "standard"))).catch((e) => setError(e.message));
  }, [leagueKey, league]);

  async function propose() {
    setBusy(true);
    setError(null);
    setProposal(null);
    try {
      const p = await api.proposeRules(leagueKey, text);
      setProposal(p);
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function decide(id: string, decision: "approve" | "decline") {
    try {
      await api.decideRule(leagueKey, id, decision);
      onChanged(decision === "approve" ? `${id} approved: standings updated 💖` : `${id} declined`);
      setProposal((p) => (p ? { ...p, rules: p.rules.filter((r) => r.id !== id) } : p));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const house = league.house_rules ?? [];
  const pending = house.filter((r) => r.status === "pending");

  return (
    <div className="grid2">
      <section>
        <h2 className="section">Add house rules</h2>
        <div className="card">
          <p className="hint">Write your league's rules the way you'd text them. The Rulesmith turns them into scoring rules,
            shows what would change, and nothing counts until you approve it.</p>
          <textarea value={text} onChange={(e) => setText(e.target.value)} placeholder={EXAMPLE} maxLength={2000} />
          <div className="row" style={{ marginTop: 10 }}>
            <button className="btn" onClick={propose} disabled={busy || text.trim().length < 3}>✨ Draft rules</button>
            <button className="btn ghost small" onClick={() => setText(EXAMPLE)} disabled={busy}>Try an example</button>
          </div>
          {busy && <Loading kind="rules" />}
          <ErrorBox error={error} />
        </div>

        {proposal && (
          <div className="card">
            <h3>Drafted for your approval <span className="muted small">({fmtUsd(proposal.cost_usd)} · {proposal.seconds}s)</span></h3>
            {proposal.rules.map((r) => (
              <div key={r.id} className="line" style={{ gridTemplateColumns: "52px 1fr auto", marginBottom: 8 }}>
                <div className="pts"><Points n={r.points} /></div>
                <div>
                  <b>{r.label}</b> {EVENT_ICONS[r.event_type]} <span className="muted small">{r.event_type}</span>
                  <div className="small muted">{describe(r)}</div>
                  <div className="receipt" style={{ fontStyle: "normal" }}>you said: “{r.original_text}”</div>
                  <div className="small">
                    {proposal.matches[r.id] === 0
                      ? <span className="badge gold">⚠ matches 0 events so far</span>
                      : <span className="badge pool">matches {proposal.matches[r.id]} event{proposal.matches[r.id] === 1 ? "" : "s"} so far</span>}
                  </div>
                </div>
                <div className="row" style={{ flexDirection: "column", gap: 6 }}>
                  <button className="btn pool small" onClick={() => decide(r.id, "approve")}>Approve</button>
                  <button className="btn ghost small" onClick={() => decide(r.id, "decline")}>Decline</button>
                </div>
              </div>
            ))}
            {proposal.unsupported.map((u, i) => (
              <div key={i} className="line" style={{ borderColor: "rgba(255,90,90,.5)", marginBottom: 8 }}>
                <div className="pts">🚫</div>
                <div><b>Can't score:</b> “{u.original_text}”<div className="small muted">{u.reason}</div></div>
              </div>
            ))}
            {proposal.impact.length > 0 && (<><h3 style={{ marginTop: 14 }}>If you approve all of them</h3><ImpactTable rows={proposal.impact} /></>)}
          </div>
        )}
      </section>

      <section>
        <h2 className="section">The rulebook</h2>
        <div className="card">
          <h3>House rules</h3>
          {house.length === 0 && <p className="muted">None yet.</p>}
          {house.map((r) => (
            <div key={r.id} className="row" style={{ justifyContent: "space-between", padding: "6px 0", borderTop: "1px solid rgba(255,255,255,.08)" }}>
              <div>
                <b>{r.label}</b> <Points n={r.points} />
                <div className="small muted">{describe(r) || r.event_type}</div>
              </div>
              {r.status === "pending" ? (
                <div className="row">
                  <button className="btn pool small" onClick={() => decide(r.id, "approve")}>Approve</button>
                  <button className="btn ghost small" onClick={() => decide(r.id, "decline")}>Decline</button>
                </div>
              ) : (
                <span className={`badge ${r.status === "approved" ? "pool" : "dim"}`}>{r.status}</span>
              )}
            </div>
          ))}
          {pending.length > 0 && <p className="small muted">{pending.length} waiting for your decision.</p>}
        </div>
        <div className="card">
          <h3>Standard points</h3>
          <table className="tbl">
            <tbody>
              {rules.map((r) => (
                <tr key={r.id}>
                  <td>{EVENT_ICONS[r.event_type]} {r.label}</td>
                  <td className="num"><Points n={r.points} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="small muted">Rules shown here are the ones in force; standard rules a house rule replaced are hidden.</p>
        </div>
      </section>
    </div>
  );
}

