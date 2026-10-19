import { useEffect, useState } from "react";

export const EVENT_ICONS: Record<string, string> = {
  entered_villa: "💣",
  re_entered: "🔁",
  coupled_up: "💞",
  stayed_coupled: "🔒",
  left_single: "💔",
  given_power: "👑",
  won_challenge: "🏆",
  date: "🍸",
  kiss: "💋",
  argument: "🔥",
  dumped: "🧳",
  left_villa: "🚪",
  finalist: "🌴",
  winner: "🥇",
  survived_week: "🌅",
};

export const EVENT_LABELS: Record<string, string> = {
  entered_villa: "Entered the villa",
  re_entered: "Re-entered",
  coupled_up: "Coupled up",
  stayed_coupled: "Stayed coupled",
  left_single: "Left single",
  given_power: "Given the power",
  won_challenge: "Won a challenge",
  date: "Date",
  kiss: "Kiss",
  argument: "Drama",
  dumped: "Dumped",
  left_villa: "Left the villa",
  finalist: "Finalist",
  winner: "Winner",
  survived_week: "Survived the week",
};

const QUIPS: Record<string, string[]> = {
  default: ["Producers are reviewing the footage…", "Checking the receipts…", "Grafting on it…"],
  scout: ["Scouting the villa gossip…", "Reading the wiki before the islanders do…", "Pulling this week's headlines…"],
  ref: ["The Ref is rewatching the tape…", "Checking the receipts…", "Consulting the villa rulebook…"],
  rules: ["Turning vibes into rules…", "Running the numbers by the pool…"],
  host: ["Your host is getting their microphone…", "Writing this week's drop…", "Adding a dramatic pause…"],
};

export function Loading({ kind = "default" }: { kind?: keyof typeof QUIPS }) {
  const lines = QUIPS[kind] ?? QUIPS.default;
  const [i, setI] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setI((n) => (n + 1) % lines.length), 2600);
    return () => clearInterval(t);
  }, [lines.length]);
  return (
    <div className="loading">
      <span className="dots"><span /><span /><span /></span>
      <span>{lines[i]}</span>
    </div>
  );
}

export function ErrorBox({ error }: { error: string | null }) {
  return error ? <div className="error">⚠️ {error}</div> : null;
}

export function Points({ n }: { n: number }) {
  return <span className={n > 0 ? "pos" : n < 0 ? "neg" : "muted"}>{n > 0 ? `+${n}` : n}</span>;
}

export function ImpactTable({ rows }: { rows: { player: string; before: number; after: number; change: number }[] }) {
  return (
    <table className="tbl">
      <thead><tr><th>Player</th><th className="num">Now</th><th className="num">If approved</th><th className="num">Change</th></tr></thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.player}>
            <td>{r.player}</td>
            <td className="num">{r.before}</td>
            <td className="num">{r.after}</td>
            <td className="num"><Points n={r.change} /></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
