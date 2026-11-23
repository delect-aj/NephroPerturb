"use client";

export function DikiBadge({ tier }: { tier?: string | null }) {
  if (!tier || tier === "NA") return <span className="badge grey">NA</span>;
  const cls = tier === "High" ? "red" : tier === "Moderate" ? "amber" : "green";
  return <span className={`badge ${cls}`}>{tier}</span>;
}

export function DirilBadge({ value }: { value?: number | string | null }) {
  if (value === 1 || value === "Positive") {
    return <span className="badge red">Positive</span>;
  }
  if (value === 0 || value === "Negative") {
    return <span className="badge green">Negative</span>;
  }
  return <span className="badge grey">—</span>;
}

export function TanimotoBar({
  value,
  decimals = 3,
}: {
  value?: number | string | null;
  decimals?: number;
}) {
  if (value == null || Number.isNaN(Number(value))) {
    return <span className="muted">—</span>;
  }
  const num = Number(value);
  const pct = Math.max(0, Math.min(100, Math.round(num * 100)));
  return (
    <div className="tanimoto-wrap">
      <span className="mono">{num.toFixed(decimals)}</span>
      <div className="tanimoto-bar">
        <div className="tanimoto-fill" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
