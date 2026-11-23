"use client";

export interface ChartItem {
  label: string;
  value: number;
}

export function HorizontalBarChart({
  items,
  color = "#2563eb",
  negativeColor = "#0ea5e9",
  height = 320,
}: {
  items: ChartItem[];
  color?: string;
  negativeColor?: string;
  height?: number;
}) {
  if (!items || items.length === 0) return null;

  const width = 620;
  const padTop = 14;
  const padBottom = 26;
  const left = 168;
  const right = 54;
  const plotW = width - left - right;
  const rowH = Math.max(22, Math.floor((Math.max(height, items.length * 26 + 40) - padTop - padBottom) / items.length));
  const svgH = padTop + padBottom + rowH * items.length;

  const vals = items.map((d) => Number(d.value) || 0);
  let minV = Math.min(0, ...vals);
  let maxV = Math.max(0, ...vals);
  if (maxV - minV < 1e-6) maxV = minV + 1;
  const span = maxV - minV;
  const xOf = (v: number) => left + ((v - minV) / span) * plotW;
  const zeroX = xOf(0);
  const ticks = minV < 0 ? [minV, 0, maxV] : [0, maxV / 2, maxV];

  return (
    <svg
      viewBox={`0 0 ${width} ${svgH}`}
      width="100%"
      style={{ display: "block", maxHeight: Math.max(height + 40, svgH) }}
      role="img"
      aria-label="Horizontal bar chart"
    >
      {ticks.map((t, idx) => {
        const x = xOf(t);
        return (
          <g key={idx}>
            <line
              x1={x}
              y1={padTop - 4}
              x2={x}
              y2={svgH - padBottom + 4}
              stroke={t === 0 ? "#94a3b8" : "#e2e8f0"}
              strokeWidth={t === 0 ? 1.3 : 1}
              strokeDasharray={t === 0 ? undefined : "3 3"}
            />
            <text
              x={x}
              y={svgH - 8}
              textAnchor="middle"
              fill="#64748b"
              fontSize="10.5"
              fontFamily="ui-monospace, monospace"
            >
              {Math.abs(t) >= 100 ? Math.round(t) : t.toFixed(1)}
            </text>
          </g>
        );
      })}

      {items.map((item, i) => {
        const v = Number(item.value) || 0;
        const x = xOf(v);
        const barX = Math.min(zeroX, x);
        const barW = Math.max(2, Math.abs(x - zeroX));
        const barH = Math.min(16, Math.max(10, rowH - 8));
        const cy = padTop + i * rowH + rowH / 2;
        const barY = cy - barH / 2;
        const valText = Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(2);
        const labelShort = item.label.length > 22 ? item.label.slice(0, 21) + "…" : item.label;

        return (
          <g key={`${i}-${item.label}`}>
            <title>{`${item.label}: ${v.toFixed(3)}`}</title>
            <text
              x={left - 8}
              y={cy + 3.5}
              textAnchor="end"
              fill="#334155"
              fontSize="11.5"
              fontWeight="500"
            >
              {labelShort}
            </text>
            <rect
              x={barX}
              y={barY}
              width={barW}
              height={barH}
              rx={3}
              fill={v >= 0 ? color : negativeColor}
              fillOpacity={0.9}
            />
            <text
              x={v >= 0 ? barX + barW + 5 : barX - 5}
              y={cy + 3.5}
              textAnchor={v >= 0 ? "start" : "end"}
              fill="#475569"
              fontSize="10.5"
              fontFamily="ui-monospace, monospace"
            >
              {valText}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

export function RadarChart({
  items,
  max = 100,
  height = 290,
}: {
  items: ChartItem[];
  max?: number;
  height?: number;
}) {
  if (!items || items.length < 3) return null;

  const w = 360;
  const h = 280;
  const cx = w / 2;
  const cy = h / 2;
  const radius = 88;
  const n = items.length;
  const angleAt = (i: number) => -Math.PI / 2 + (2 * Math.PI * i) / n;
  const ptAt = (i: number, frac: number) => {
    const a = angleAt(i);
    return [cx + radius * frac * Math.cos(a), cy + radius * frac * Math.sin(a)];
  };

  const rings = [0.25, 0.5, 0.75, 1.0];
  const polyPoints = items
    .map((it, i) => {
      const f = Math.max(0, Math.min(1, (Number(it.value) || 0) / max));
      const [x, y] = ptAt(i, f);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      width="100%"
      style={{ display: "block", height, maxWidth: "100%" }}
      role="img"
      aria-label="Component tau radar chart"
    >
      {rings.map((frac) => {
        const pts = items
          .map((_, i) => ptAt(i, frac).map((v) => v.toFixed(1)).join(","))
          .join(" ");
        return (
          <g key={frac}>
            <polygon
              points={pts}
              fill={frac === 1 ? "#f8fafc" : "none"}
              stroke="#cbd5e1"
              strokeWidth={frac === 1 ? 1.2 : 0.9}
              strokeDasharray={frac === 1 ? undefined : "3 3"}
            />
            <text
              x={cx + 4}
              y={cy - radius * frac + 3}
              fill="#94a3b8"
              fontSize="9.5"
              fontFamily="ui-monospace, monospace"
            >
              {Math.round(max * frac)}
            </text>
          </g>
        );
      })}

      {items.map((it, i) => {
        const [ox, oy] = ptAt(i, 1);
        const [lx, ly] = ptAt(i, 1.23);
        const anchor = Math.abs(lx - cx) < 10 ? "middle" : lx > cx ? "start" : "end";
        return (
          <g key={it.label}>
            <line x1={cx} y1={cy} x2={ox} y2={oy} stroke="#cbd5e1" strokeWidth="1" />
            <text
              x={lx}
              y={ly + 4}
              textAnchor={anchor}
              fill="#0f172a"
              fontSize="11.5"
              fontWeight="600"
            >
              {`${it.label} (${Math.round(Number(it.value) || 0)})`}
            </text>
          </g>
        );
      })}

      <polygon
        points={polyPoints}
        fill="#14b8a6"
        fillOpacity="0.25"
        stroke="#2563eb"
        strokeWidth="2.2"
        strokeLinejoin="round"
      />

      {items.map((it, i) => {
        const f = Math.max(0, Math.min(1, (Number(it.value) || 0) / max));
        const [vx, vy] = ptAt(i, f);
        return (
          <circle key={it.label} cx={vx} cy={vy} r="4" fill="#2563eb" stroke="#ffffff" strokeWidth="1.5">
            <title>{`${it.label}: ${Number(it.value || 0).toFixed(1)}`}</title>
          </circle>
        );
      })}
    </svg>
  );
}
