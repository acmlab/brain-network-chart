import { useEffect, useState } from 'react';
import { ToastContainer } from './app_test1/toast.jsx';
import { FloatingLLMChat } from './app_test1/FloatingLLMChat.jsx';
import { HomePage } from './app_test1/HomePage.jsx';
import { LoadingPage } from './app_test1/LoadingPage.jsx';
import { BrainChartView } from './app_test1/BrainChartView.jsx';
import { NetworkAnalysisView } from './app_test1/NetworkAnalysisView.jsx';

export default function UnifiedBrainApp() {
  const [activeView, setActiveView] = useState('home');
  const [isLoading, setIsLoading] = useState(true);
  const [chatOpen, setChatOpen] = useState(false);
  const [chatMessages, setChatMessages] = useState([
    { role: 'assistant', content: 'Hi! I can help interpret your analysis results.' }
  ]);
  const [chatInput, setChatInput] = useState('');
  const [selectedTask, setSelectedTask] = useState(null);
  const [selectedWindow, setSelectedWindow] = useState(0);

  useEffect(() => { setTimeout(() => setIsLoading(false), 1500); }, []);

  const handleSendChat = async () => {
    const content = chatInput.trim();
    if (!content) return;
    const nextMessages = [...chatMessages, { role: 'user', content }];
    setChatMessages(nextMessages);
    setChatInput('');
    try {
      const res = await fetch('/api/chat', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: nextMessages, task_id: selectedTask, window_idx: selectedWindow }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'LLM request failed');
      const reply = data.response || data.message || '';
      setChatMessages(prev => [...prev, { role: 'assistant', content: reply || '(No response)' }]);
    } catch (err) { setChatMessages(prev => [...prev, { role: 'assistant', content: `Error: ${err.message}` }]); }
  };

  const getViewTitle = () => {
    switch (activeView) {
      case 'cfc': return { title: 'CFC Wavelet Analysis', subtitle: 'Cross-Frequency Coupling using Harmonic Wavelets' };
      case 'hub': return { title: 'Hub Detection Analysis', subtitle: 'Detect hub nodes using Grassmann manifold optimization' };
      case 'chart': return { title: 'BrainChart Analysis', subtitle: 'Lifespan normative growth curves for brain phenotypes' };
      default: return { title: '', subtitle: '' };
    }
  };

  if (isLoading) return <LoadingPage />;

  const { title, subtitle } = getViewTitle();
  const navItems = [
    { id: 'home', label: 'Home', icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6' },
    { id: 'cfc', label: 'CFC', icon: 'M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z' },
    { id: 'hub', label: 'Hub', icon: 'M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z' },
    { id: 'chart', label: 'BrainChart', icon: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z' },
  ];

  return (
    <div className="min-h-screen flex flex-col bg-slate-100">
      <ToastContainer />

      {/* Header */}
      <header className="flex-shrink-0 h-14 px-4 md:px-6 flex items-center justify-between bg-white border-b border-slate-200 shadow-sm sticky top-0 z-40">
        <button onClick={() => setActiveView('home')} className="flex items-center gap-2.5 text-slate-800 hover:text-indigo-600 transition-colors">
          <span className="w-9 h-9 rounded-lg bg-slate-850 flex items-center justify-center">
            <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
          </span>
          <span className="font-semibold text-base tracking-tight hidden sm:inline">Brain Suite</span>
        </button>

        <nav className="flex items-center gap-0.5">
          {navItems.map((item) => (
            <button key={item.id} onClick={() => setActiveView(item.id)}
              className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                activeView === item.id ? 'bg-indigo-500 text-white shadow-sm' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
              }`}>
              <svg className="w-4 h-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d={item.icon} />
              </svg>
              <span className="hidden md:inline">{item.label}</span>
            </button>
          ))}
        </nav>

        <button onClick={() => setChatOpen(!chatOpen)}
          className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
            chatOpen ? 'bg-slate-700 text-white' : 'bg-slate-850 text-white hover:bg-slate-800'
          }`} title="AI Assistant">
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
          </svg>
          <span className="hidden sm:inline">AI</span>
        </button>
      </header>

      {/* Main */}
      <main className="flex-1 flex flex-col min-h-0">
        {activeView === 'home' ? (
          <HomePage onNavigate={setActiveView} />
        ) : (
          <>
            <div className="flex-shrink-0 px-4 md:px-6 py-2.5 bg-white/80 backdrop-blur-sm border-b border-slate-200/60">
              <h1 className="text-sm font-semibold text-slate-800">{title}</h1>
              <p className="text-xs text-slate-500 mt-0.5">{subtitle}</p>
            </div>
            <div className="flex-1 min-h-0 overflow-auto bg-slate-50">
              {(activeView === 'cfc' || activeView === 'hub') && <NetworkAnalysisView mode={activeView} />}
              {activeView === 'chart' && <BrainChartView />}
            </div>
          </>
        )}
      </main>

      <FloatingLLMChat
        isOpen={chatOpen}
        onToggle={() => setChatOpen(!chatOpen)}
        messages={chatMessages}
        input={chatInput}
        onInputChange={setChatInput}
        onSend={handleSendChat}
      />

      <style>{`
        @keyframes slide-up { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes fade-in  { from { opacity: 0; } to { opacity: 1; } }
        .animate-slide-up { animation: slide-up 0.3s cubic-bezier(0.16, 1, 0.3, 1) forwards; }
        .animate-fade-in  { animation: fade-in 0.45s ease-out forwards; }
      `}</style>
    </div>
  );
}
