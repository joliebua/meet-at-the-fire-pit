import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { api, fmtUsd, type FinaleAdvice, type FinaleState, type StandingRow } from "../api";
import { ErrorBox, Loading } from "./common";

const FirePitScene = lazy(() => import("./three/FirePitScene"));

type Props = { leagueKey: string; onChanged: (msg?: string) => void; celebrate: () => void };

const money = (n: number) => (Number.isInteger(n) ? `$${n}` : `$${n.toFixed(2)}`);

/** Share or take it all? The two finalists' sealed envelopes, opened at the fire pit. */
export default function Finale({ leagueKey, onChanged, celebrate }: Props) {
  const [st, setSt] = useState<FinaleState | null>(null);
  const [standings, setStandings] = useState<StandingRow[]>([]);
  const [prize, setPrize] = useState(100);
  const [advice, setAdvice] = useState<FinaleAdvice | null>(null);
  const [busy, setBusy] = useState("");
  const [flipped, setFlipped] = useState(0); // how many envelopes are open on screen
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.finale(leagueKey)
      .then((s) => {
        setSt(s);
        setFlipped(s.finale?.revealed ? 2 : 0);
        if (s.complete) return api.standings(leagueKey, s.final_week).then((r) => setStandings(r.standings));
      })
      .catch((e) => setError(e.message));
  }, [leagueKey]);

  const f = st?.finale;
  // The two finalists go first (they stand by the fire), then everyone else on the couches in rank order.
  const seats = useMemo(() => {
    const names = f?.finalists.map((p) => p.player) ?? [];
    const ordered = [...standings].sort((a, b) => {
      const ia = names.indexOf(a.player), ib = names.indexOf(b.player);
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
    }).slice(0, 4);
    return ordered.map((r) => {
      const isFinalist = names.includes(r.player);
      const choice = f?.revealed && flipped >= 2 ? f.choices?.[r.player] : undefined;
      const rank = standings.findIndex((x) => x.player === r.player) + 1;
      return {
        label: r.player, value: r.total, highlight: r.player === st?.you,
        sub: isFinalist ? (choice === "share" ? "💞 shared" : choice === "take" ? "💰 took it all" : "finalist") : `#${rank}`,
      };
    });
  }, [standings, f, flipped, st?.you]);

  if (!st || !st.complete) return error ? <ErrorBox error={error} /> : null;

  const run = async (kind: string, fn: () => Promise<void>) => {
    setBusy(kind);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  };
  const handOut = () => run("start", async () => {
    setSt(await api.finaleStart(leagueKey, prize));
    setAdvice(null);
    setFlipped(0);
    onChanged("✉️ The host has handed out the envelopes");
  });
  const seal = (player: string, choice: "share" | "take") => run("seal", async () => {
    setSt(await api.envelope(leagueKey, player, choice));
    setAdvice(null);
    onChanged(`${player}'s envelope is sealed 🔒`);
  });
  const ask = () => run("coach", async () => setAdvice(await api.finaleAdvice(leagueKey)));
  const reveal = () => run("reveal", async () => {
    const s = await api.finaleReveal(leagueKey);
    setSt(s);
    setFlipped(0);
    // Open the envelopes one at a time, like the show.
    await new Promise((r) => setTimeout(r, 900));
    setFlipped(1);
    await new Promise((r) => setTimeout(r, 1600));
    setFlipped(2);
    const choices = Object.values(s.finale?.choices ?? {});
    if (choices.includes("share")) celebrate();
    onChanged("🔥 The envelopes are open");
  });
  const again = () => run("reset", async () => {
    await api.finaleReset(leagueKey);
    setSt(await api.finale(leagueKey));
    setAdvice(null);
    setFlipped(0);
  });

  const bothTook = f?.revealed && flipped >= 2 && Object.values(f.choices ?? {}).every((c) => c === "take");
  const humansLeft = f ? f.finalists.filter((p) => !f.bots.includes(p.player) && !f.sealed[p.player]) : [];

  return (
    <section className={`finale ${bothTook ? "flare" : ""}`}>
      <div className="card finale-card">
        <h2 className="section" style={{ margin: 0 }}>🏆 The finale: share or take it all?</h2>
        <p className="hint" style={{ margin: "6px 0 0" }}>
          The season is over. The top two meet at the fire pit with a sealed envelope each. <b>Both share</b>: split the pot.
          <b> One takes</b>: they get it all. <b>Both take</b>: nobody gets anything. <span className="muted">(The pot is pretend: no real money moves through the app.)</span>
        </p>
        {!f && (
          <div className="row" style={{ marginTop: 12 }}>
            <label className="field" style={{ margin: 0 }}>Pot $</label>
            <input type="number" min={1} max={1000000} value={prize} onChange={(e) => setPrize(Number(e.target.value) || 1)} style={{ width: 110 }} />
            <button className="btn" onClick={handOut} disabled={!!busy}>✉️ Hand out the envelopes</button>
          </div>
        )}
        <ErrorBox error={error} />
      </div>

      {f && (
        <>
          <Suspense fallback={<div style={{ height: 320 }} />}>
            <FirePitScene seats={seats} height={320} mode="standings" standers={2} envelopes />
          </Suspense>
          <div className="envelopes">
            {f.finalists.map((p, i) => {
              const isBot = f.bots.includes(p.player);
              const sealed = f.sealed[p.player];
              const open = f.revealed && flipped > i;
              const choice = f.choices?.[p.player];
              return (
                <div key={p.player} className={`env-card ${open ? "flipped" : ""}`}>
                  <div className="env-inner">
                    <div className="env-face env-front">
                      <div className="env-name">{p.player}{p.player === st.you ? " ⭐" : ""}</div>
                      <div className="small muted">#{i + 1} · {p.total} pts</div>
                      <div className="env-icon">{sealed || f.revealed ? "✉️" : "📩"}</div>
                      {!f.revealed && sealed && <div className="badge pool">🔒 sealed</div>}
                      {!f.revealed && !sealed && isBot && <div className="small">🤖 decides at the reveal</div>}
                      {!f.revealed && !sealed && !isBot && (
                        <div className="env-actions">
                          {st.mode === "classic" && <div className="small muted">Pass the phone: {p.player}, choose privately</div>}
                          <div className="row" style={{ justifyContent: "center" }}>
                            <button className="btn pool small" onClick={() => seal(p.player, "share")} disabled={!!busy}>💞 Share</button>
                            <button className="btn small" onClick={() => seal(p.player, "take")} disabled={!!busy}>💰 Take it all</button>
                          </div>
                          {st.mode === "play" && p.player === st.you && (
                            <button className="btn ghost small" onClick={ask} disabled={!!busy}>🎯 Ask the Strategist</button>
                          )}
                        </div>
                      )}
                    </div>
                    <div className={`env-face env-back ${choice}`}>
                      <div className="env-name">{p.player}</div>
                      <div className="env-choice">{choice === "share" ? "💞 SHARE" : "💰 TAKE IT ALL"}</div>
                      <div className="env-amount">{money(f.payout?.[p.player] ?? 0)}</div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
          {busy === "coach" && <Loading kind="coach" />}
          {advice && (
            <div className="card coach">
              <div className="row" style={{ justifyContent: "space-between" }}>
                <span className="coach-title">🎯 Villa Strategist</span>
                <span className="small muted">{fmtUsd(advice.cost_usd)} · {advice.seconds}s · can't see the other envelope</span>
              </div>
              <p style={{ lineHeight: 1.5 }}><b>{advice.advice.choice === "share" ? "💞 Share" : "💰 Take it all"}.</b> {advice.advice.reason}</p>
            </div>
          )}
          <div className="card" style={{ textAlign: "center" }}>
            {!f.revealed && (
              <button className="btn bigplay" onClick={reveal} disabled={!!busy || humansLeft.length > 0}>
                {humansLeft.length ? `Waiting for ${humansLeft.map((p) => p.player).join(" & ")}…` : "🔥 Open the envelopes"}
              </button>
            )}
            {busy === "reveal" && <Loading kind="host" />}
            {f.revealed && flipped >= 2 && (
              <>
                <p className="host-line">🎙️ {f.host_line}</p>
                <button className="btn ghost small" onClick={again} disabled={!!busy}>↺ Run the finale again</button>
              </>
            )}
          </div>
        </>
      )}
    </section>
  );
}
