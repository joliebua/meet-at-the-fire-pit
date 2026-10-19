import { useEffect, useState } from "react";
import { api, fmtUsd, type Dispute, type Impact, type League } from "../api";
import { ErrorBox, EVENT_ICONS, EVENT_LABELS, ImpactTable, Loading } from "./common";

type Props = { leagueKey: string; league: League; onChanged: (msg?: string) => void };

const VERDICT = { uphold: "Upheld 💖", partial: "Partly upheld", deny: "Denied 🙅" } as const;

function RulingCard({ d, impact, steps, cost, onDecide }: {
  d: Dispute; impact?: Impact[]; steps?: string[]; cost?: string; onDecide?: (id: string, ok: boolean) => void;
}) {
  const r = d.ruling;
  return (
    <div className={`card ruling ${r.verdict}`}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div className="verdict">{VERDICT[r.verdict]}</div>
        <div className="row">
          {r.injection_suspected && <span className="badge bad">🛡️ manipulation attempt blocked</span>}
          <span className={`badge ${d.status === "approved" ? "pool" : d.status === "pending" ? "gold" : "dim"}`}>{d.status}</span>
        </div>
      </div>
      <p className="small muted" style={{ margin: "4px 0 8px" }}>{d.id} · {d.player}: “{d.text}”</p>
      <p style={{ margin: "0 0 8px", lineHeight: 1.5 }}>{r.explanation}</p>
      {r.add_events.map((e, i) => (
        <div key={i} className="event" style={{ marginBottom: 8 }}>
          <div className="icon">{EVENT_ICONS[e.type]}</div>
          <div>
            <b>Add: {EVENT_LABELS[e.type] ?? e.type}: {e.islanders.join(" & ")}</b> <span className="muted small">{e.week}{e.day ? ` · Day ${e.day}` : ""}</span>
            <div className="receipt">“{e.evidence[0]?.quote}” <span className="muted">({e.evidence[0]?.source_id})</span></div>
            <span className="badge pool small">✓ receipt verified by code</span>
          </div>
        </div>
      ))}
      {r.remove_event_ids.map((id) => <div key={id} className="small">➖ Remove event <code>{id}</code></div>)}
      {steps && steps.length > 0 && (
        <div className="steps" title="What the Ref looked at">{steps.map((s, i) => <span key={i}>{s}</span>)}</div>
      )}
      {impact && impact.some((x) => x.change !== 0) && <div style={{ marginTop: 10 }}><ImpactTable rows={impact} /></div>}
      {cost && <p className="small muted" style={{ marginBottom: 0 }}>{cost}</p>}
      {d.status === "pending" && onDecide && (
        <div className="row" style={{ marginTop: 12 }}>
          <button className="btn pool" onClick={() => onDecide(d.id, true)}>Approve ruling</button>
          <button className="btn ghost" onClick={() => onDecide(d.id, false)}>Decline</button>
        </div>
      )}
    </div>
  );
}

export default function Disputes({ leagueKey, league, onChanged }: Props) {
  const [player, setPlayer] = useState(league.players[0]?.name ?? "");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [latest, setLatest] = useState<Awaited<ReturnType<typeof api.fileDispute>> | null>(null);
  const [history, setHistory] = useState<Dispute[]>(league.disputes ?? []);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => setHistory(league.disputes ?? []), [league]);

  async function file() {
    setBusy(true);
    setError(null);
    setLatest(null);
    try {
      const r = await api.fileDispute(leagueKey, player, text);
      setLatest(r);
      setText("");
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function decide(id: string, ok: boolean) {
    try {
      const d = await api.decideDispute(leagueKey, id, ok ? "approve" : "decline");
      setLatest((cur) => (cur && cur.dispute.id === id ? { ...cur, dispute: d } : cur));
      onChanged(ok ? `${id} approved: points updated 💖` : `${id} declined`);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const past = [...history].reverse().filter((d) => d.id !== latest?.dispute.id);

  return (
    <div className="grid2">
      <section>
        <h2 className="section">File a dispute</h2>
        <div className="card">
          <p className="hint">Think your islander was robbed? The Ref rewatches the receipts. It can only add or remove events
            the sources actually back up, never hand out points, and the commissioner signs off on every ruling.</p>
          <label className="field">Who's complaining?</label>
          <select value={player} onChange={(e) => setPlayer(e.target.value)} style={{ marginBottom: 10 }}>
            {league.players.map((p) => <option key={p.name}>{p.name}</option>)}
          </select>
          <label className="field">What did we get wrong?</label>
          <textarea value={text} onChange={(e) => setText(e.target.value)} maxLength={1000}
                    placeholder="e.g. Corbin got kissed by all the girls in the secret room on Day 5 but got zero kiss points." />
          <button className="btn" style={{ marginTop: 10 }} onClick={file} disabled={busy || text.trim().length < 3}>⚖️ Send to the Ref</button>
          {busy && <Loading kind="ref" />}
          <ErrorBox error={error} />
        </div>
        {latest && (
          <RulingCard d={latest.dispute} impact={latest.impact} steps={latest.steps} onDecide={decide}
                      cost={`${fmtUsd(latest.cost_usd)} · ${latest.seconds}s`} />
        )}
      </section>
      <section>
        <h2 className="section">Past rulings</h2>
        {past.length === 0 && <div className="card muted">No disputes yet. Suspiciously peaceful villa.</div>}
        {past.map((d) => <RulingCard key={d.id} d={d} onDecide={decide} />)}
      </section>
    </div>
  );
}
