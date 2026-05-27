"use client";

import type { HistoryPoint } from "@/lib/api";

type Props = {
  data: HistoryPoint[];
};

export function PriceChart({ data }: Props) {
  const clean = data
    .filter((d) => d.open != null && d.high != null && d.low != null && d.close != null)
    .slice(-80);

  if (clean.length < 2) {
    return (
      <div className="flex h-72 items-center justify-center rounded-lg border border-dashed border-zinc-300 bg-white text-sm text-zinc-500">
        暂无足够 K 线数据
      </div>
    );
  }

  const width = 920;
  const height = 320;
  const priceHeight = 238;
  const volumeTop = 255;
  const pad = 18;
  const highs = clean.map((d) => Number(d.high));
  const lows = clean.map((d) => Number(d.low));
  const volumes = clean.map((d) => Number(d.volume || 0));
  const maxPrice = Math.max(...highs);
  const minPrice = Math.min(...lows);
  const maxVolume = Math.max(...volumes, 1);
  const span = Math.max(maxPrice - minPrice, 1);
  const step = (width - pad * 2) / clean.length;
  const candleWidth = Math.max(Math.min(step * 0.56, 9), 3);

  const y = (value: number) => pad + ((maxPrice - value) / span) * (priceHeight - pad);
  const volumeY = (value: number) => volumeTop + (1 - value / maxVolume) * 46;

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="h-80 w-full rounded-lg border bg-white shadow-sm"
      role="img"
      aria-label="Candlestick and volume chart"
    >
      <rect x="0" y="0" width={width} height={height} fill="#ffffff" />
      {[0, 1, 2, 3].map((tick) => {
        const yy = pad + tick * 58;
        return <line key={tick} x1={pad} x2={width - pad} y1={yy} y2={yy} stroke="#e5e7eb" strokeWidth="1" />;
      })}
      {clean.map((d, index) => {
        const open = Number(d.open);
        const close = Number(d.close);
        const high = Number(d.high);
        const low = Number(d.low);
        const volume = Number(d.volume || 0);
        const x = pad + index * step + step / 2;
        const up = close >= open;
        const color = up ? "#0f9f6e" : "#d92d20";
        const bodyTop = Math.min(y(open), y(close));
        const bodyHeight = Math.max(Math.abs(y(open) - y(close)), 1.8);
        const vTop = volumeY(volume);
        return (
          <g key={`${d.date}-${index}`}>
            <line x1={x} x2={x} y1={y(high)} y2={y(low)} stroke={color} strokeWidth="1.4" />
            <rect
              x={x - candleWidth / 2}
              y={bodyTop}
              width={candleWidth}
              height={bodyHeight}
              fill={up ? "#ffffff" : color}
              stroke={color}
              strokeWidth="1.2"
            />
            <rect
              x={x - candleWidth / 2}
              y={vTop}
              width={candleWidth}
              height={Math.max(301 - vTop, 1)}
              fill={color}
              opacity="0.18"
            />
          </g>
        );
      })}
      <text x={pad} y={314} fill="#71717a" fontSize="11">
        {clean[0]?.date}
      </text>
      <text x={width - pad - 82} y={314} fill="#71717a" fontSize="11">
        {clean[clean.length - 1]?.date}
      </text>
      <text x={width - 92} y={28} fill="#52525b" fontSize="11">
        {maxPrice.toFixed(2)}
      </text>
      <text x={width - 92} y={priceHeight} fill="#52525b" fontSize="11">
        {minPrice.toFixed(2)}
      </text>
    </svg>
  );
}
