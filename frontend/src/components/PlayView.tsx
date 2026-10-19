import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { api, fmtPts, fmtUsd, type AdvanceResult, type Advice, type IslanderFacts, type PlayState } from "../api";
import { ErrorBox, EVENT_ICONS, EVENT_LABELS, Loading, Points } from "./common";

const FirePitScene = lazy(() => import("./three/FirePitScene"));

type Props = {
  leagueKey: string | null;
  goToFinale?: () => void;
  onCreated: (key: string) => void;
  onChanged: (msg?: string) => void;
  celebrate: () => void;
};

function StartCard({ onCreated }: { onCreated: (key: string) => void }) {
  const [name, setName] = useState("My Villa League");
  const [you, setYou] = useState("Jolie");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function create() {
    setBusy(true);
    setError(null);
    try {
      const s = await api.createPlay(name, you);
      onCreated(s.key);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="card" style={{ maxWidth: 620 }}>
      <h2 className="section">Start a play-along league</h2>
      <p className="hint">You and three bot friends (Maya, Dev and Priya) draft islanders after Day 2, then play Love Island USA
        season 8 one week at a time. The <b>Villa Strategist</b> coaches your picks and weekly moves, or runs your team on autopilot.
        Nobody, including the AI, gets to see past the current week.</p>
      <div className="row" style={{ alignItems: "flex-end" }}>
        <div><label className="field">League name</label><input value={name} onChange={(e) => setName(e.target.value)} maxLength={60} /></div>
        <div><label className="field">Your name</label><input value={you} onChange={(e) => setYou(e.target.value)} maxLength={20} /></div>
        <button className="btn" onClick={create} disabled={busy || !name.trim() || !you.trim()}>🌴 Enter the villa</button>
      </div>
      <ErrorBox error={error} />
    </div>
  );
}

function IslanderCard({ f, action, suggested, owner }: { f: IslanderFacts; action?: React.ReactNode; suggested?: string; owner?: string }) {
  const last = f.events[f.events.length - 1];
  return (
    <div className={`icard ${suggested ? "suggested" : ""}`}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <span className="iname">{f.name}</span>
        <b><Points n={f.points} /></b>
      </div>
      <div className="small">
        {!f.in_villa ? <span className="badge bad">🧳 left the villa</span>
          : f.partner ? <span className="badge hot">💞 with {f.partner}</span> : <span className="badge dim">single</span>}
        {owner && <span className="badge dim" style={{ marginLeft: 6 }}>{owner}</span>}
      </div>
      {last && <div className="quote">{EVENT_ICONS[last.type]} {EVENT_LABELS[last.type]}{last.day ? ` · Day ${last.day}` : ""}: “{last.quote.slice(0, 110)}{last.quote.length > 110 ? "…" : ""}”</div>}
      {suggested && <div className="small" style={{ color: "var(--gold)" }}>🎯 {suggested}</div>}
      {action}
    </div>
  );
}

function CoachCard({ advice, children }: { advice: Advice; children?: React.ReactNode }) {
  return (
    <div className="card coach">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <span className="coach-title">🎯 Villa Strategist</span>
        <span className="small muted">{fmtUsd(advice.cost_usd)} · {advice.seconds}s</span>
      </div>
      <p style={{ lineHeight: 1.5 }}>{advice.advice.summary}</p>
      {children}
      <div className="steps" title="What the Strategist looked at">{advice.steps.map((s, i) => <span key={i}>{s}</span>)}</div>
    </div>
  );
}

export default function PlayView({ leagueKey, onCreated, onChanged, celebrate, goToFinale }: Props) {
  const [state, setState] = useState<PlayState | null>(null);
  const [advice, setAdvice] = useState<Advice | null>(null);
  const [result, setResult] = useState<AdvanceResult | null>(null);
  const [busy, setBusy] = useState<"" | "coach" | "pick" | "play" | "move">("");
  const [error, setError] = useState<string | null>(null);
  const [addPick, setAddPick] = useState("");
  const [dropPick, setDropPick] = useState("");

  useEffect(() => {
    setState(null);
    setAdvice(null);
    setResult(null);
    if (leagueKey) api.play(leagueKey).then(setState).catch((e) => setError(e.message));
  }, [leagueKey]);

  const seats = useMemo(
    () => [...(state?.your_roster ?? [])].sort((a, b) => b.points - a.points).map((f) => ({
      label: f.name, value: f.points, highlight: true, partner: f.in_villa ? f.partner : null, left: !f.in_villa,
      sub: f.in_villa ? (f.partner ? `💞 ${f.partner}` : "single") : "🧳 left the villa",
    })),
    [state],
  );

  if (!leagueKey) return <StartCard onCreated={onCreated} />;
  if (!state) return error ? <ErrorBox error={error} /> : <Loading />;

  const key = leagueKey;
  const run = async <T,>(kind: typeof busy, fn: () => Promise<T>) => {
    setBusy(kind);
    setError(null);
    try {
      return await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  };

  const askCoach = () => run("coach", async () => setAdvice(await api.advice(key)));
  const draft = (name: string) => run("pick", async () => {
    const r = await api.pick(key, name);
    setState(r.state);
    setAdvice(null);
    celebrate();
    onChanged(`You drafted ${name} 💖`);
  });
  const doMove = (add: string | null, drop: string | null, reason = "") => run("move", async () => {
    const r = await api.move(key, add, drop, reason);
    setState(r.state);
    setAdvice(null);
    setAddPick("");
    setDropPick("");
    celebrate();
    onChanged(add ? `${add} is on your team from next week 💞` : `${drop} released`);
  });
  const play = () => run("play", async () => {
    const r = await api.advance(key);
    setResult(r);
    setState(r.state);
    setAdvice(null);
    onChanged(`${r.week} is in! ${fmtPts(r.standings.find((s) => s.player === state.you)?.change ?? 0)} for you`);
    if (r.state.current_week >= r.state.max_week || r.standings[0]?.player === state.you) celebrate();
  });
  const toggleAutopilot = (on: boolean) => run("move", async () => {
    await api.autopilot(key, on);
    setState({ ...state, settings: { ...state.settings, autopilot: on } });
  });

  const suggested = new Map((advice?.advice.picks ?? []).map((p) => [p.islander, p.reason]));
  const owners = Object.fromEntries(Object.entries(state.rosters).flatMap(([p, names]) => names.map((n) => [n, p])));

  // ---------------- draft ----------------
  if (!state.draft.done) {
    const total = state.draft.order.length * state.settings.draft_rounds;
    const yourTurn = state.draft.turn === state.you;
    return (
      <section>
        <div className="card">
          <div className="row" style={{ justifyContent: "space-between" }}>
            <div>
              <h2 className="section" style={{ margin: 0 }}>The draft</h2>
              <p className="hint" style={{ margin: "4px 0 0" }}>Snake draft after Day {state.settings.draft_after_day} · pick {state.draft.picks.length + 1} of {total}
                · then rosters grow to {state.settings.roster_max} with weekly pickups as bombshells arrive.</p>
            </div>
            {yourTurn && <button className="btn" onClick={askCoach} disabled={!!busy}>🎯 Ask the Strategist</button>}
          </div>
          <div className="order" style={{ marginTop: 10 }}>
            {state.draft.order.map((p) => <span key={p} className={p === state.draft.turn ? "now" : ""}>{p === state.you ? `⭐ ${p}` : p}</span>)}
          </div>
          {yourTurn && <p style={{ marginBottom: 0 }}><b>It's your pick!</b></p>}
          {busy === "coach" && <Loading kind="coach" />}
          {busy === "pick" && <Loading />}
          <ErrorBox error={error} />
        </div>
        {advice && (
          <CoachCard advice={advice}>
            <ol style={{ paddingLeft: 20 }}>
              {(advice.advice.picks ?? []).map((p) => (
                <li key={p.islander} style={{ marginBottom: 8 }}>
                  <b>{p.islander}</b>: {p.reason}{" "}
                  <button className="btn small" onClick={() => draft(p.islander)} disabled={!!busy}>Draft {p.islander}</button>
                </li>
              ))}
            </ol>
          </CoachCard>
        )}
        <div className="card">
          <h3>Available islanders</h3>
          <div className="pool-grid">
            {state.free_agents.map((f) => (
              <IslanderCard key={f.name} f={f} suggested={suggested.get(f.name)}
                action={yourTurn && <button className="btn small" onClick={() => draft(f.name)} disabled={!!busy}>Draft</button>} />
            ))}
          </div>
        </div>
        {state.draft.picks.length > 0 && (
          <div className="card">
            <h3>Picks so far</h3>
            <div className="timeline">
              {state.draft.picks.map((p) => (
                <div key={p.pick}><b>#{p.pick} {p.player}</b> → {p.islander} <span className="muted small">({p.by}{p.reason ? `: ${p.reason}` : ""})</span></div>
              ))}
            </div>
          </div>
        )}
      </section>
    );
  }

  // ---------------- season ----------------
  const over = state.current_week >= state.max_week;
  const next = state.current_week + 1;
  const rosterFull = state.your_roster.length >= state.settings.roster_max;
  const myRow = state.standings.find((r) => r.player === state.you);
  const rank = state.standings.findIndex((r) => r.player === state.you) + 1;

  return (
    <section>
      <Suspense fallback={<div style={{ height: 320 }}><Loading /></div>}>
        <FirePitScene seats={seats} height={320} mode="team"
          caption={`Your team on the fire pit couches, each next to their partner · points so far (through Week ${state.current_week})`} />
      </Suspense>

      <div className="card" style={{ marginTop: 16 }}>
        <div className="row" style={{ justifyContent: "space-between" }}>
          <div>
            <h2 className="section" style={{ margin: 0 }}>{over ? "🏆 Season complete" : state.current_week === 0 ? "Draft done: ready for Week 1" : `Week ${state.current_week} of ${state.max_week} played`}</h2>
            <p className="hint" style={{ margin: "4px 0 0" }}>
              {myRow && state.current_week > 0 ? <>You're <b>#{rank}</b> with <b>{myRow.total}</b> points. </> : null}
              {over ? <>That's the season. <button className="btn small" onClick={goToFinale}>🔥 To the finale: share or take it all?</button></> :
                <>Moves you make now count from Week {next}. You have <b>{state.moves_left}</b> move left this week. Bots move when you press play.</>}
            </p>
          </div>
          {!over && (
            <div className="row">
              <label className="switch" title="The Strategist makes your weekly move for you, within the league rules">
                <input type="checkbox" checked={state.settings.autopilot} onChange={(e) => toggleAutopilot(e.target.checked)} disabled={!!busy} />
                <span className="track" /> 🤖 Autopilot
              </label>
              <button className="btn ghost" onClick={askCoach} disabled={!!busy}>🎯 Ask the Strategist</button>
              <button className="btn bigplay" onClick={play} disabled={!!busy}>▶ Play Week {next}</button>
            </div>
          )}
        </div>
        {busy === "play" && <Loading kind={state.settings.autopilot ? "coach" : "default"} />}
        {busy === "coach" && <Loading kind="coach" />}
        <ErrorBox error={error} />
      </div>

      {advice && advice.kind === "moves" && (
        <CoachCard advice={advice}>
          {(advice.advice.moves ?? []).length === 0 && <p className="muted">No move this week: hold your team.</p>}
          {(advice.advice.moves ?? []).map((m, i) => (
            <div key={i} className="line" style={{ gridTemplateColumns: "1fr auto", marginBottom: 8 }}>
              <div>
                <b>{m.add ? `➕ ${m.add}` : ""}{m.add && m.drop ? "  " : ""}{m.drop ? `➖ ${m.drop}` : ""}</b>
                <div className="small" style={{ marginTop: 2 }}>{m.reason}</div>
                {m.evidence.map((q, j) => <div key={j} className="receipt">“{q}”</div>)}
              </div>
              <button className="btn pool small" onClick={() => doMove(m.add, m.drop, m.reason)} disabled={!!busy || state.moves_left < 1}>Make this move</button>
            </div>
          ))}
        </CoachCard>
      )}

      {result && (
        <div className="card">
          <h3>{result.week} results</h3>
          <div className="grid2">
            <div>
              <div className="small muted" style={{ marginBottom: 6 }}>Your points this week</div>
              <div className="ledger" style={{ maxHeight: 260 }}>
                {result.your_points.slice(0, 8).map((l, i) => (
                  <div className="line" key={i}>
                    <div className="pts"><Points n={l.points} /></div>
                    <div><b>{l.islander}</b> · {l.label}
                      {l.source_id !== "code" && <div className="receipt">“{l.quote.slice(0, 120)}{l.quote.length > 120 ? "…" : ""}”</div>}</div>
                  </div>
                ))}
                {result.your_points.length === 0 && <p className="muted">Quiet week for your team.</p>}
              </div>
            </div>
            <div>
              <table className="tbl">
                <thead><tr><th>#</th><th>Player</th><th className="num">Total</th><th className="num">This week</th></tr></thead>
                <tbody>{result.standings.map((r, i) => (
                  <tr key={r.player} style={r.player === state.you ? { color: "var(--gold)" } : undefined}>
                    <td>{i + 1}</td><td>{r.player}</td><td className="num">{r.total}</td><td className="num"><Points n={r.change} /></td>
                  </tr>))}
                </tbody>
              </table>
              {result.autopilot_moves.map((m, i) => <p key={i} className="small">🤖 Autopilot: {m.add ? `added ${m.add}` : ""}{m.drop ? ` dropped ${m.drop}` : ""}. {m.reason}</p>)}
              {result.bot_moves.map((m, i) => <p key={i} className="small muted">{m.player}: {m.add ? `+${m.add}` : ""} {m.drop ? `−${m.drop}` : ""}</p>)}
            </div>
          </div>
        </div>
      )}

      <div className="grid2">
        <div className="card">
          <h3>Your team for Week {over ? state.current_week : next}</h3>
          <div className="pool-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
            {state.your_roster.map((f) => <IslanderCard key={f.name} f={f} />)}
          </div>
          {!over && (
            <div className="row" style={{ marginTop: 12 }}>
              <select value={addPick} onChange={(e) => setAddPick(e.target.value)}>
                <option value="">Pick up…</option>
                {state.free_agents.map((f) => <option key={f.name} value={f.name}>{f.name} ({fmtPts(f.points)})</option>)}
              </select>
              <select value={dropPick} onChange={(e) => setDropPick(e.target.value)}>
                <option value="">{rosterFull ? "Drop… (needed)" : "Drop (optional)"}</option>
                {state.your_roster.map((f) => <option key={f.name} value={f.name}>{f.name}</option>)}
              </select>
              <button className="btn small" onClick={() => doMove(addPick || null, dropPick || null)}
                disabled={!!busy || state.moves_left < 1 || (!addPick && !dropPick)}>Make move</button>
            </div>
          )}
        </div>
        <div className="card">
          <h3>Free agents in the villa</h3>
          {state.free_agents.length === 0 && <p className="muted">Everyone in the villa is on a team. Wait for the next bombshell…</p>}
          <div className="pool-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
            {state.free_agents.slice(0, 6).map((f) => <IslanderCard key={f.name} f={f} owner={owners[f.name]} />)}
          </div>
        </div>
      </div>

      {state.moves.length > 0 && (
        <div className="card">
          <h3>Moves log</h3>
          <div className="timeline">
            {[...state.moves].reverse().map((m, i) => (
              <div key={i}>
                <b>{m.player}</b> {m.add && <>➕ {m.add}</>} {m.drop && <>➖ {m.drop}</>}
                <span className="muted small"> · for Week {m.from_week} · {m.by === "autopilot" ? "🤖 autopilot" : m.by}{m.reason ? `: ${m.reason}` : ""}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
