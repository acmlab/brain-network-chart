export const LoadingPage = () => (
  <div className="fixed inset-0 bg-slate-850 flex items-center justify-center z-50">
    <div className="text-center">
      <div className="relative w-24 h-24 mx-auto mb-8 flex items-center justify-center">
        <div className="absolute inset-0 border-2 border-white/15 border-t-white rounded-full animate-spin" />
        <div className="w-16 h-16 rounded-xl bg-white/10 flex items-center justify-center">
          <svg className="w-8 h-8 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
          </svg>
        </div>
      </div>
      <h2 className="text-2xl font-semibold text-white mb-2 tracking-tight">Loading Brain Tools</h2>
      <p className="text-white/60 text-sm">Initializing analysis modules…</p>
    </div>
  </div>
);
