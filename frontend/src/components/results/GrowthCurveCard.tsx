import { useMemo } from 'react'
import {
  ComposedChart, CartesianGrid, Legend, Line, ResponsiveContainer,
  Scatter, Tooltip, XAxis, YAxis,
} from 'recharts'
import type { GrowthCurveResult } from '../../types'

interface Props {
  data: GrowthCurveResult
  timestamp: string
}

function fmtVal(v: number): string {
  const abs = Math.abs(v)
  if (abs === 0) return '0'
  if (abs >= 0.01) return v.toFixed(4)
  return v.toPrecision(4)
}

export default function GrowthCurveCard({ data, timestamp }: Props) {
  const chartData = useMemo(() => {
    if (!data.data) return []
    const { X, centiles } = data.data
    return X.map((x, i) => ({
      age: x,
      p5: centiles[i]?.[0],
      p25: centiles[i]?.[1],
      p50: centiles[i]?.[2],
      p75: centiles[i]?.[3],
      p95: centiles[i]?.[4],
    }))
  }, [data.data])

  const xAxisDomain = useMemo((): [number, number] => {
    if (chartData.length === 0) return [0, 80]
    return [chartData[0].age, chartData[chartData.length - 1].age]
  }, [chartData])

  const yAxisDomain = useMemo((): [number, number] => {
    if (chartData.length === 0) return [0, 1]
    let min = Infinity, max = -Infinity
    chartData.forEach(d => {
      [d.p5, d.p25, d.p50, d.p75, d.p95].forEach(val => {
        if (val !== undefined) { if (val < min) min = val; if (val > max) max = val }
      })
    })
    const margin = (max - min) * 0.1
    return [min - margin, max + margin]
  }, [chartData])

  return (
    <div className="result-card">
      <div className="result-card-header">
        <span className="result-card-title">{data.phenotype}</span>
        <span className="result-card-time">{timestamp}</span>
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        <div className="stat-box" style={{ flex: 1 }}>
          <div className="stat-label">Elapsed (s)</div>
          <div className="stat-value" style={{ color: '#a5b4fc' }}>{data.elapsed_seconds.toFixed(2)}</div>
        </div>
        <div className="stat-box" style={{ flex: 1 }}>
          <div className="stat-label">Age Range</div>
          <div className="stat-value" style={{ fontSize: 13 }}>
            {chartData.length > 0 ? `${chartData[0].age.toFixed(0)}–${chartData[chartData.length - 1].age.toFixed(0)} yr` : '—'}
          </div>
        </div>
        {data.overlay && (
          <div className="stat-box" style={{ flex: 1 }}>
            <div className="stat-label">Overlay Points</div>
            <div className="stat-value" style={{ color: '#f87171' }}>{data.overlay.age.length}</div>
          </div>
        )}
      </div>

      {chartData.length > 0 ? (
        <ResponsiveContainer width="100%" height={280}>
          <ComposedChart data={chartData} margin={{ top: 10, right: 16, left: 0, bottom: 16 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e2235" />
            <XAxis
              dataKey="age"
              label={{ value: 'Age (yr)', position: 'insideBottom', offset: -8, style: { fontSize: 11, fill: '#64748b' } }}
              type="number"
              domain={xAxisDomain}
              tick={{ fontSize: 10, fill: '#64748b' }}
            />
            <YAxis
              domain={yAxisDomain}
              width={72}
              tick={{ fontSize: 10, fill: '#64748b' }}
              tickFormatter={v => fmtVal(v)}
            />
            <Tooltip
              contentStyle={{ background: '#1a1d2e', border: '1px solid #2d3250', borderRadius: 8, fontSize: 11 }}
              labelStyle={{ color: '#a5b4fc' }}
              itemStyle={{ color: '#e2e8f0' }}
              formatter={(v: number) => fmtVal(v)}
              labelFormatter={v => `Age: ${Number(v).toFixed(1)} yr`}
            />
            <Legend iconType="line" iconSize={12} verticalAlign="top"
              wrapperStyle={{ fontSize: 11, paddingBottom: 4 }} />
            <Line dataKey="p5"  stroke="#475569" strokeWidth={1.5} strokeDasharray="5 4" dot={false} name="5th" />
            <Line dataKey="p25" stroke="#7c3aed" strokeWidth={1.5} strokeDasharray="5 4" dot={false} name="25th" />
            <Line dataKey="p50" stroke="#a5b4fc" strokeWidth={2.5} dot={false} name="50th (Median)" />
            <Line dataKey="p75" stroke="#7c3aed" strokeWidth={1.5} strokeDasharray="5 4" dot={false} name="75th" />
            <Line dataKey="p95" stroke="#475569" strokeWidth={1.5} strokeDasharray="5 4" dot={false} name="95th" />
            {data.overlay && (
              <Scatter
                data={data.overlay.age.map((a, i) => ({ age: a, value: data.overlay!.values[i] }))}
                dataKey="value"
                fill="#f87171"
                name="Your data"
              />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      ) : (
        <div style={{ textAlign: 'center', padding: '24px 0', color: '#4b5563', fontSize: 13 }}>
          No curve data available
        </div>
      )}
    </div>
  )
}
