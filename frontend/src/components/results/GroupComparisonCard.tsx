import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import type { GroupComparisonResult } from '../../types'

interface Props {
  data: GroupComparisonResult
  timestamp: string
}

const GROUP_COLORS = ['#818cf8', '#34d399']

export default function GroupComparisonCard({ data, timestamp }: Props) {
  const chartData = [
    { name: data.group_a || 'Group A', mean: data.mean_group_1 },
    { name: data.group_b || 'Group B', mean: data.mean_group_2 },
  ]

  const effectColor =
    data.effect_size === 'Large' ? '#f87171' :
    data.effect_size === 'Medium' ? '#fb923c' :
    data.effect_size === 'Small' ? '#facc15' : '#4b5563'

  return (
    <div className="result-card">
      <div className="result-card-header">
        <span className="result-card-title">{data.test_used}</span>
        <span className="result-card-time">{timestamp}</span>
      </div>

      <ResponsiveContainer width="100%" height={160}>
        <BarChart data={chartData} margin={{ top: 8, right: 8, bottom: 0, left: -20 }}>
          <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 12 }} axisLine={false} tickLine={false} />
          <YAxis tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} />
          <Tooltip
            contentStyle={{ background: '#1a1d2e', border: '1px solid #2d3250', borderRadius: 8, fontSize: 12 }}
            labelStyle={{ color: '#a5b4fc' }}
            itemStyle={{ color: '#e2e8f0' }}
            formatter={(v: number) => v.toFixed(4)}
          />
          <Bar dataKey="mean" radius={[4, 4, 0, 0]} maxBarSize={60}>
            {chartData.map((_, i) => <Cell key={i} fill={GROUP_COLORS[i]} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      <div className="stat-grid" style={{ gridTemplateColumns: 'repeat(3, 1fr)', marginTop: 8 }}>
        <div className="stat-box">
          <div className="stat-label">p-value</div>
          <div className="stat-value" style={{ fontSize: 14 }}>
            {data.p_value < 0.001 ? '< 0.001' : data.p_value.toFixed(4)}
          </div>
        </div>
        <div className="stat-box">
          <div className="stat-label">Cohen's d</div>
          <div className="stat-value" style={{ fontSize: 14 }}>{data.cohens_d.toFixed(3)}</div>
        </div>
        <div className="stat-box">
          <div className="stat-label">Effect Size</div>
          <div className="stat-value" style={{ fontSize: 13, color: effectColor }}>{data.effect_size}</div>
        </div>
      </div>

      <div style={{ marginTop: 10 }}>
        <span className={`badge ${data.significant ? 'badge-sig' : 'badge-nonsig'}`}>
          {data.significant ? 'Significant (p < 0.05)' : 'Not Significant'}
        </span>
      </div>

      <div className="explanation">{data['Explanation of results']}</div>
    </div>
  )
}
