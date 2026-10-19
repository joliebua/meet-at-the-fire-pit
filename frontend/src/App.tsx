import { useCallback, useEffect, useState } from "react";
import { api, weekNum, type AppConfig, type League, type WeekInfo } from "./api";
import { ErrorBox, Loading } from "./components/common";
import Leaderboard from "./components/Leaderboard";
import Villa from "./components/Villa";
import HouseRules from "./components/HouseRules";
import Disputes from "./components/Disputes";
import DropView from "./components/Drop";
import Costs from "./components/Costs";

const LEAGUE = "demo_league";

const TABS = [
  { id: "board", label: "🏝️ Leaderboard" },
  { id: "villa", label: "📺 This Week in the Villa" },
  { id: "drop", label: "🎙️ The Drop" },
  { id: "rules", label: "📜 House Rules" },
  { id: "disputes", label: "⚖️ Disputes" },
  { id: "costs", label: "💸 Cost to Run" },
] as const;
type Tab = (typeof TABS)[number]["id"];

export default function App() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [league, setLeague] = useState<League | null>(null);
  const [weeks, setWeeks] = useState<WeekInfo[]>([]);
  const [watched, setWatched] = useState<number | null>(null);
  const [tab, setTab] = useState<Tab>("board");
  const [version, setVersion] = useState(0); // bump to refetch after any change
  const [toast, setToast] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const changed = useCallback((message?: string) => {
    setVersion((v) => v + 1);
    if (message) {
      setToast(message);
      setTimeout(() => setToast(null), 3500);
    }
  }, []);

  useEffect(() => {
    api.config().then(setConfig).catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    api.league(LEAGUE)
      .then((lg) => {
        setLeague(lg);
        return api.weeks(lg.season);
      })
      .then((ws) => {
        setWeeks(ws);
        const recapped = ws.filter((w) => w.recapped).map((w) => weekNum(w.week));
        setWatched((cur) => cur ?? (recapped.length ? Math.max(...recapped) : null));
      })
      .catch((e) => setError(e.message));
  }, [version]);

  const recappedWeeks = weeks.filter((w) => w.recapped);
  const show = league && config ? config.seasons[league.season] : null;

  return (
    <div className="app">
      <header className="topbar">
        <h1 className="logo">Villa Commissioner <span className="heart">♥</span></h1>
        <div className="league-name">
          <strong>{league?.name ?? "…"}</strong>
          {show && <> · {show.show} season {show.season}</>}
        </div>
        <div className="spacer" />
        {config && (
          <span className={`badge ${config.source_mode === "live" ? "hot" : "pool"}`}
                title={config.source_mode === "live" ? "Gathering from live wiki, news and web search" : "Replaying the saved snapshot offline"}>
            {config.source_mode === "live" ? "🔴 Live sources" : "💾 Snapshot mode"}
          </span>
        )}
        {recappedWeeks.length > 0 && watched !== null && (
          <label className="watch" title="Spoiler shield: scores and drops only use weeks you've watched">
            🙈 I've watched through
            <select value={watched} onChange={(e) => setWatched(Number(e.target.value))}>
              {recappedWeeks.map((w) => (
                <option key={w.week} value={weekNum(w.week)}>{w.week}</option>
              ))}
            </select>
          </label>
        )}
      </header>

      <nav className="tabs">
        {TABS.map((t) => (
          <button key={t.id} className={`tab ${tab === t.id ? "active" : ""}`} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </nav>

      <ErrorBox error={error} />
      {!league || watched === null ? (
        !error && <Loading />
      ) : (
        <main>
          {tab === "board" && <Leaderboard leagueKey={LEAGUE} league={league} week={watched} version={version} />}
          {tab === "villa" && <Villa league={league} weeks={weeks} watched={watched} version={version} onChanged={changed} />}
          {tab === "drop" && <DropView leagueKey={LEAGUE} week={watched} version={version} onChanged={changed} />}
          {tab === "rules" && <HouseRules leagueKey={LEAGUE} league={league} onChanged={changed} />}
          {tab === "disputes" && <Disputes leagueKey={LEAGUE} league={league} onChanged={changed} />}
          {tab === "costs" && <Costs version={version} weeksScored={recappedWeeks.length} players={league.players.length} />}
        </main>
      )}

      {toast && <div className="toast">{toast}</div>}
      <footer className="foot">
        Fan-made fantasy league tool · not affiliated with Love Island, ITV or Peacock · every point has a receipt
        {config && <> · model {config.model}</>}
      </footer>
    </div>
  );
}
