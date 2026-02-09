export const HomePage = ({ onNavigate }) => {
  const features = [
    {
      id: 'cfc',
      title: 'CFC Wavelet Analysis',
      description: 'Cross-Frequency Coupling using Harmonic Wavelets for brain signal analysis',
      icon: (
        <svg className="w-12 h-12" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
        </svg>
      ),
      color: 'from-blue-500 to-cyan-500',
      stats: ['Time-Frequency Analysis', 'Wavelet Decomposition', 'Coupling Metrics'],
    },
    {
      id: 'hub',
      title: 'Hub Detection',
      description: 'Detect hub nodes in brain networks using Grassmann manifold optimization',
      icon: (
        <svg className="w-12 h-12" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
        </svg>
      ),
      color: 'from-purple-500 to-pink-500',
      stats: ['Network Topology', 'Hub Identification', 'Manifold Optimization'],
    },
    {
      id: 'chart',
      title: 'BrainChart',
      description: 'Lifespan normative growth curves for brain phenotypes and measurements',
      icon: (
        <svg className="w-12 h-12" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
        </svg>
      ),
      color: 'from-emerald-500 to-teal-500',
      stats: ['Growth Curves', 'Centile Analysis', 'Age Normalization'],
    },
  ];

  return (
    <div className="flex-1 min-h-0 overflow-auto bg-slate-50">
      <div className="max-w-5xl mx-auto px-4 md:px-6 py-8 md:py-10">
        <div className="mb-10 animate-fade-in">
          <h1 className="text-2xl md:text-3xl font-bold text-slate-800 tracking-tight mb-2">
            Brain Network Analysis Suite
          </h1>
          <p className="text-slate-500 max-w-2xl">
            Advanced tools for brain signal analysis, network topology detection, and normative growth curve modeling.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mb-8">
          {features.map((feature, idx) => (
            <button
              key={feature.id}
              type="button"
              onClick={() => onNavigate(feature.id)}
              className="group text-left bg-white rounded-2xl border border-slate-200 overflow-hidden transition-all duration-200 hover:shadow-lg hover:border-indigo-300 hover:-translate-y-0.5 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:ring-offset-2 animate-slide-up"
              style={{ animationDelay: `${idx * 80}ms` }}
            >
              <div className={`bg-gradient-to-br ${feature.color} p-5 text-white`}>
                <div className="flex justify-center mb-2 opacity-95">{feature.icon}</div>
                <h2 className="text-lg font-semibold text-center tracking-tight">{feature.title}</h2>
              </div>
              <div className="p-4">
                <p className="text-slate-500 text-sm leading-relaxed mb-3">{feature.description}</p>
                <ul className="space-y-1.5 mb-4">
                  {feature.stats.map((stat, i) => (
                    <li key={i} className="flex items-center text-xs text-slate-500">
                      <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 mr-2" />
                      {stat}
                    </li>
                  ))}
                </ul>
                <span className={`inline-flex items-center gap-1.5 py-1.5 px-3 rounded-lg text-xs font-semibold bg-gradient-to-r ${feature.color} text-white`}>
                  Open
                  <svg className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M13 7l5 5m0 0l-5 5m5-5H6" />
                  </svg>
                </span>
              </div>
            </button>
          ))}
        </div>

        <p className="text-center text-slate-400 text-xs">Powered by advanced ML and signal processing</p>
      </div>
    </div>
  );
};
