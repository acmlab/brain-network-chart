import { useState, useEffect, useRef } from 'react';

/* ═══════════════════════════════════════════════════════════════════════════
   DATA TYPES & CONSTANTS
   
   AgentStatus shape:
   {
     id: string,            // "planner" | "executor" | "researcher" | "validator"
     name: string,          // display name
     model: string,         // LLM model used
     port: number,          // A2A server port
     status: string,        // "idle" | "waiting" | "running" | "completed" | "error"
     currentStep: string,   // what the agent is doing right now
     messages: string[],    // log of agent outputs
     startTime: number|null,
     endTime: number|null,
     error: string|null,
   }

   WorkflowState shape:
   {
     query: string,
     agents: AgentStatus[],
     phase: string,         // "idle"|"planning"|"executing"|"researching"|"validating"|"done"|"error"
     overallProgress: number, // 0-100
   }
   ═══════════════════════════════════════════════════════════════════════════ */

const AGENT_DEFINITIONS = [
  { id: 'planner',    name: 'Planner',    model: 'MedGemma',  port: 8011, icon: '📋', role: 'Parse query & create task plan' },
  { id: 'executor',   name: 'Executor',   model: 'MedGemma',  port: 8012, icon: '⚙️', role: 'MCP tools & input-to-trait analysis' },
  { id: 'researcher', name: 'Researcher', model: 'TxGemma',   port: 8013, icon: '🔬', role: 'Database search & statistical analysis' },
  { id: 'validator',  name: 'Validator',  model: 'TxGemma',   port: 8014, icon: '✅', role: 'Validate all agent outputs' },
];

const STATUS_CONFIG = {
  idle:      { label: 'Idle',       bg: 'bg-slate-100',    text: 'text-slate-500',   dot: 'bg-slate-300',    ring: 'ring-slate-200',   lineDone: false },
  waiting:   { label: 'Waiting',    bg: 'bg-amber-50',     text: 'text-amber-700',   dot: 'bg-amber-400',    ring: 'ring-amber-200',   lineDone: false },
  running:   { label: 'Running',    bg: 'bg-sky-50',       text: 'text-sky-700',     dot: 'bg-sky-500',      ring: 'ring-sky-300',     lineDone: false },
  completed: { label: 'Completed',  bg: 'bg-emerald-50',   text: 'text-emerald-700', dot: 'bg-emerald-500',  ring: 'ring-emerald-300', lineDone: true  },
  error:     { label: 'Error',      bg: 'bg-red-50',       text: 'text-red-700',     dot: 'bg-red-500',      ring: 'ring-red-300',     lineDone: false },
};

const PHASE_LABELS = {
  idle:         'Waiting for query',
  planning:     'Planning tasks…',
  executing:    'Executing analysis…',
  researching:  'Researching literature…',
  validating:   'Validating results…',
  done:         'Workflow complete',
  error:        'Workflow error',
};


/* ═══════════════════════════════════════════════════════════════════════════
   MOCK DATA
   ═══════════════════════════════════════════════════════════════════════════ */

function createInitialAgents() {
  return AGENT_DEFINITIONS.map(def => ({
    ...def,
    status: 'idle',
    currentStep: '',
    messages: [],
    startTime: null,
    endTime: null,
    error: null,
  }));
}

const MOCK_SCENARIOS = {
  idle: {
    label: 'Idle',
    state: {
      query: '',
      phase: 'idle',
      overallProgress: 0,
      agents: createInitialAgents(),
    },
  },
  planning: {
    label: 'Planning',
    state: {
      query: 'Analyze BOLD signal for cross-frequency coupling in prefrontal cortex',
      phase: 'planning',
      overallProgress: 10,
      agents: (() => {
        const a = createInitialAgents();
        a[0] = { ...a[0], status: 'running', currentStep: 'Parsing user query and creating execution plan…',
          messages: ['Received query', 'Identifying analysis type: CFC Wavelet', 'Assigning tasks to Executor, Researcher, Validator…'],
          startTime: Date.now() - 3000 };
        a[1] = { ...a[1], status: 'waiting', currentStep: 'Waiting for plan from Planner' };
        a[2] = { ...a[2], status: 'waiting', currentStep: 'Waiting for keywords from Executor' };
        a[3] = { ...a[3], status: 'waiting', currentStep: 'Waiting for all results' };
        return a;
      })(),
    },
  },
  executing: {
    label: 'Executing',
    state: {
      query: 'Analyze BOLD signal for cross-frequency coupling in prefrontal cortex',
      phase: 'executing',
      overallProgress: 35,
      agents: (() => {
        const a = createInitialAgents();
        a[0] = { ...a[0], status: 'completed', currentStep: 'Plan created',
          messages: ['Received query', 'Identified analysis: CFC Wavelet', 'Plan: 1) Executor runs CFC 2) Researcher searches PubMed 3) Validator checks results'],
          startTime: Date.now() - 12000, endTime: Date.now() - 8000 };
        a[1] = { ...a[1], status: 'running', currentStep: 'Running CFC wavelet analysis via MCP…',
          messages: ['Selected tool: run_cfc_wavelet_analysis', 'Config: window=50, step=3, wavelets=10', 'Processing BOLD signal…', 'Extracting coupling metrics…'],
          startTime: Date.now() - 8000 };
        a[2] = { ...a[2], status: 'waiting', currentStep: 'Waiting for keywords from Executor' };
        a[3] = { ...a[3], status: 'waiting', currentStep: 'Waiting for all results' };
        return a;
      })(),
    },
  },
  researching: {
    label: 'Researching',
    state: {
      query: 'Analyze BOLD signal for cross-frequency coupling in prefrontal cortex',
      phase: 'researching',
      overallProgress: 60,
      agents: (() => {
        const a = createInitialAgents();
        a[0] = { ...a[0], status: 'completed', currentStep: 'Plan created',
          messages: ['Received query', 'Identified analysis: CFC Wavelet', 'Plan distributed to agents'],
          startTime: Date.now() - 25000, endTime: Date.now() - 20000 };
        a[1] = { ...a[1], status: 'completed', currentStep: 'Analysis complete',
          messages: ['Tool: run_cfc_wavelet_analysis', 'Config applied', 'CFC matrix generated (10×10)', 'Keywords: theta-gamma coupling, prefrontal cortex, wavelet coherence'],
          startTime: Date.now() - 20000, endTime: Date.now() - 10000 };
        a[2] = { ...a[2], status: 'running', currentStep: 'Searching PubMed for "theta-gamma coupling prefrontal cortex"…',
          messages: ['Received keywords from Executor', 'Querying PubMed…', 'Found 23 relevant papers', 'Running statistical analysis on findings…'],
          startTime: Date.now() - 10000 };
        a[3] = { ...a[3], status: 'waiting', currentStep: 'Waiting for all results' };
        return a;
      })(),
    },
  },
  validating: {
    label: 'Validating',
    state: {
      query: 'Analyze BOLD signal for cross-frequency coupling in prefrontal cortex',
      phase: 'validating',
      overallProgress: 85,
      agents: (() => {
        const a = createInitialAgents();
        a[0] = { ...a[0], status: 'completed', currentStep: 'Plan created',
          messages: ['Plan distributed to agents'],
          startTime: Date.now() - 40000, endTime: Date.now() - 35000 };
        a[1] = { ...a[1], status: 'completed', currentStep: 'Analysis complete',
          messages: ['CFC matrix generated (10×10)', 'Keywords extracted'],
          startTime: Date.now() - 35000, endTime: Date.now() - 22000 };
        a[2] = { ...a[2], status: 'completed', currentStep: 'Research complete',
          messages: ['23 PubMed papers found', 'Statistical analysis done', 'Config update: not needed'],
          startTime: Date.now() - 22000, endTime: Date.now() - 8000 };
        a[3] = { ...a[3], status: 'running', currentStep: 'Validating executor and researcher outputs…',
          messages: ['Checking CFC results against query', 'Cross-referencing with literature', 'Computing confidence score…'],
          startTime: Date.now() - 8000 };
        return a;
      })(),
    },
  },
  done: {
    label: 'Done',
    state: {
      query: 'Analyze BOLD signal for cross-frequency coupling in prefrontal cortex',
      phase: 'done',
      overallProgress: 100,
      agents: (() => {
        const a = createInitialAgents();
        a[0] = { ...a[0], status: 'completed', currentStep: 'Plan created',
          messages: ['Plan distributed to agents'],
          startTime: Date.now() - 50000, endTime: Date.now() - 45000 };
        a[1] = { ...a[1], status: 'completed', currentStep: 'Analysis complete',
          messages: ['CFC matrix generated (10×10)', 'Keywords extracted'],
          startTime: Date.now() - 45000, endTime: Date.now() - 30000 };
        a[2] = { ...a[2], status: 'completed', currentStep: 'Research complete',
          messages: ['23 PubMed papers found', 'Statistical analysis done'],
          startTime: Date.now() - 30000, endTime: Date.now() - 15000 };
        a[3] = { ...a[3], status: 'completed', currentStep: 'Validation passed',
          messages: ['Query answered: Yes', 'Confidence: 92%', 'No issues found'],
          startTime: Date.now() - 15000, endTime: Date.now() - 2000 };
        return a;
      })(),
    },
  },
  error: {
    label: 'Error',
    state: {
      query: 'Analyze BOLD signal for cross-frequency coupling in prefrontal cortex',
      phase: 'error',
      overallProgress: 40,
      agents: (() => {
        const a = createInitialAgents();
        a[0] = { ...a[0], status: 'completed', currentStep: 'Plan created',
          messages: ['Plan distributed to agents'],
          startTime: Date.now() - 20000, endTime: Date.now() - 15000 };
        a[1] = { ...a[1], status: 'error', currentStep: 'MCP tool call failed',
          messages: ['Tool: run_cfc_wavelet_analysis', 'Config applied', 'ERROR: Connection to MCP server refused (port 8010)'],
          startTime: Date.now() - 15000, endTime: Date.now() - 8000,
          error: 'Connection refused: http://yukon.acm.unc.edu:8010/run_cfc_wavelet_analysis' };
        a[2] = { ...a[2], status: 'idle', currentStep: 'Blocked — waiting for Executor' };
        a[3] = { ...a[3], status: 'idle', currentStep: 'Blocked — waiting for all results' };
        return a;
      })(),
    },
  },
};


/* ═══════════════════════════════════════════════════════════════════════════
   UTILITY
   ═══════════════════════════════════════════════════════════════════════════ */

function formatDuration(startMs, endMs) {
  if (!startMs) return '—';
  const elapsed = (endMs || Date.now()) - startMs;
  const sec = Math.floor(elapsed / 1000);
  if (sec < 60) return `${sec}s`;
  return `${Math.floor(sec / 60)}m ${sec % 60}s`;
}


/* ═══════════════════════════════════════════════════════════════════════════
   SUB-COMPONENTS
   ═══════════════════════════════════════════════════════════════════════════ */

const PulsingDot = ({ className }) => (
  <span className="relative flex h-3 w-3">
    <span className={`absolute inline-flex h-full w-full rounded-full opacity-60 animate-ping ${className}`} />
    <span className={`relative inline-flex h-3 w-3 rounded-full ${className}`} />
  </span>
);

const TimelineNode = ({ status }) => {
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.idle;

  if (status === 'running') {
    return (
      <div className={`relative z-10 flex items-center justify-center w-8 h-8 rounded-full bg-white ring-2 ${cfg.ring} shadow-sm`}>
        <PulsingDot className={cfg.dot} />
      </div>
    );
  }
  if (status === 'completed') {
    return (
      <div className={`relative z-10 flex items-center justify-center w-8 h-8 rounded-full ${cfg.dot} ring-2 ${cfg.ring} shadow-sm`}>
        <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
        </svg>
      </div>
    );
  }
  if (status === 'error') {
    return (
      <div className={`relative z-10 flex items-center justify-center w-8 h-8 rounded-full ${cfg.dot} ring-2 ${cfg.ring} shadow-sm`}>
        <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </div>
    );
  }
  return (
    <div className={`relative z-10 flex items-center justify-center w-8 h-8 rounded-full bg-white ring-2 ${cfg.ring} shadow-sm`}>
      <span className={`w-2.5 h-2.5 rounded-full ${cfg.dot}`} />
    </div>
  );
};

const AgentTimelineCard = ({ agent, isLast, expanded, onToggle, onPause, onRetry }) => {
  const cfg = STATUS_CONFIG[agent.status] || STATUS_CONFIG.idle;
  const messagesEndRef = useRef(null);

  useEffect(() => {
    if (expanded && messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [expanded, agent.messages.length]);

  return (
    <div className="relative flex gap-4">
      {/* Timeline spine */}
      <div className="flex flex-col items-center">
        <TimelineNode status={agent.status} />
        {!isLast && (
          <div className={`w-0.5 flex-1 mt-1 transition-colors duration-500 ${
            cfg.lineDone ? 'bg-emerald-300' : 'bg-slate-200'
          }`} />
        )}
      </div>

      {/* Card */}
      <div className={`flex-1 mb-6 rounded-xl border transition-all duration-200 overflow-hidden ${
        agent.status === 'running'
          ? 'border-sky-200 bg-sky-50/60 shadow-sm'
          : agent.status === 'error'
          ? 'border-red-200 bg-red-50/40'
          : agent.status === 'completed'
          ? 'border-emerald-200 bg-emerald-50/30'
          : 'border-slate-200 bg-white'
      }`}>
        {/* Header */}
        <button onClick={onToggle} className="w-full flex items-center justify-between px-4 py-3 text-left group">
          <div className="flex items-center gap-3 min-w-0">
            <span className="text-lg flex-shrink-0">{agent.icon}</span>
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-sm font-semibold text-slate-800">{agent.name}</span>
                <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${cfg.bg} ${cfg.text}`}>
                  {cfg.label}
                </span>
              </div>
              <p className="text-xs text-slate-500 mt-0.5 truncate max-w-xs">{agent.currentStep || agent.role}</p>
            </div>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0 ml-2">
            {agent.startTime && (
              <span className="text-[10px] font-mono text-slate-400 bg-slate-100 px-1.5 py-0.5 rounded">
                {formatDuration(agent.startTime, agent.endTime)}
              </span>
            )}
            <span className="text-[10px] font-mono text-slate-400 bg-slate-100 px-1.5 py-0.5 rounded hidden sm:inline">
              {agent.model}
            </span>
            <svg className={`w-4 h-4 text-slate-400 transition-transform duration-200 ${expanded ? 'rotate-180' : ''}`}
              fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
            </svg>
          </div>
        </button>

        {/* Expanded detail */}
        {expanded && (
          <div className="px-4 pb-4 border-t border-slate-100/80">
            <div className="flex items-center gap-3 mt-3 mb-3 text-[11px] text-slate-400">
              <span>Port: <span className="font-mono text-slate-600">{agent.port}</span></span>
              <span className="text-slate-200">|</span>
              <span>Model: <span className="font-mono text-slate-600">{agent.model}</span></span>
              {agent.startTime && (
                <>
                  <span className="text-slate-200">|</span>
                  <span>Duration: <span className="font-mono text-slate-600">{formatDuration(agent.startTime, agent.endTime)}</span></span>
                </>
              )}
            </div>

            {agent.error && (
              <div className="mb-3 flex items-start gap-2 p-2.5 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700">
                <svg className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                </svg>
                <span className="font-mono break-all">{agent.error}</span>
              </div>
            )}

            {agent.messages.length > 0 && (
              <div className="bg-slate-900 rounded-lg p-3 max-h-36 overflow-y-auto font-mono text-[11px] leading-relaxed">
                {agent.messages.map((msg, i) => (
                  <div key={i} className="flex gap-2">
                    <span className="text-slate-600 select-none flex-shrink-0">{String(i + 1).padStart(2, '0')}</span>
                    <span className={`${
                      msg.startsWith('ERROR') ? 'text-red-400' :
                      msg.startsWith('WARNING') ? 'text-amber-400' :
                      'text-emerald-400'
                    }`}>{msg}</span>
                  </div>
                ))}
                <div ref={messagesEndRef} />
              </div>
            )}

            <div className="flex items-center gap-2 mt-3">
              {agent.status === 'running' && (
                <button onClick={(e) => { e.stopPropagation(); onPause(agent.id); }}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-amber-50 text-amber-700 border border-amber-200 hover:bg-amber-100 active:bg-amber-200 transition-colors">
                  <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zM7 8a1 1 0 012 0v4a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v4a1 1 0 102 0V8a1 1 0 00-1-1z" clipRule="evenodd" />
                  </svg>
                  Pause
                </button>
              )}
              {agent.status === 'error' && (
                <button onClick={(e) => { e.stopPropagation(); onRetry(agent.id); }}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-sky-50 text-sky-700 border border-sky-200 hover:bg-sky-100 active:bg-sky-200 transition-colors">
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
                  Retry
                </button>
              )}
              {agent.status === 'completed' && (
                <span className="text-[11px] text-emerald-600 font-medium flex items-center gap-1">
                  <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                  </svg>
                  Finished
                </span>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};


/* ═══════════════════════════════════════════════════════════════════════════
   MAIN: AgentProgressPanel
   
   Props (for future real integration):
     workflow: WorkflowState
     onPause:  (agentId) => void
     onRetry:  (agentId) => void
   ═══════════════════════════════════════════════════════════════════════════ */

export default function AgentProgressPanel({ workflow: externalWorkflow, onPause: externalOnPause, onRetry: externalOnRetry } = {}) {
  const [mockScenario, setMockScenario] = useState('idle');
  const [expandedAgents, setExpandedAgents] = useState({});
  const [showDebug, setShowDebug] = useState(true);

  const workflow = externalWorkflow || MOCK_SCENARIOS[mockScenario].state;

  const toggleExpand = (agentId) => {
    setExpandedAgents(prev => ({ ...prev, [agentId]: !prev[agentId] }));
  };

  useEffect(() => {
    const autoExpand = {};
    workflow.agents.forEach(a => {
      if (a.status === 'running' || a.status === 'error') {
        autoExpand[a.id] = true;
      }
    });
    setExpandedAgents(prev => ({ ...prev, ...autoExpand }));
  }, [mockScenario, workflow.phase]);

  const handlePause = (agentId) => {
    if (externalOnPause) { externalOnPause(agentId); return; }
    console.log(`[AgentProgressPanel] Pause requested for: ${agentId}`);
    alert(`Pause agent: ${agentId}\n\n(Will call POST /api/agent/${agentId}/pause when backend is ready)`);
  };

  const handleRetry = (agentId) => {
    if (externalOnRetry) { externalOnRetry(agentId); return; }
    console.log(`[AgentProgressPanel] Retry requested for: ${agentId}`);
    alert(`Retry agent: ${agentId}\n\n(Will call POST /api/agent/${agentId}/retry when backend is ready)`);
  };

  const completedCount = workflow.agents.filter(a => a.status === 'completed').length;
  const totalCount = workflow.agents.length;

  return (
    <div className="flex flex-col h-full min-h-0 bg-slate-50/50 rounded-xl overflow-hidden" style={{ maxHeight: '100vh' }}>
      {/* Header */}
      <div className="flex-shrink-0 px-4 py-3 bg-white border-b border-slate-200">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <span className="w-7 h-7 rounded-lg bg-slate-900 flex items-center justify-center">
              <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
              </svg>
            </span>
            <div>
              <h3 className="text-sm font-semibold text-slate-800">Agent Workflow</h3>
              <p className="text-[11px] text-slate-400 mt-0.5">
                {PHASE_LABELS[workflow.phase] || workflow.phase}
                {workflow.phase !== 'idle' && ` — ${completedCount}/${totalCount} agents`}
              </p>
            </div>
          </div>
          {workflow.phase !== 'idle' && (
            <span className={`text-xs font-bold px-2 py-1 rounded-lg ${
              workflow.phase === 'done' ? 'bg-emerald-100 text-emerald-700' :
              workflow.phase === 'error' ? 'bg-red-100 text-red-700' :
              'bg-sky-100 text-sky-700'
            }`}>{workflow.overallProgress}%</span>
          )}
        </div>
        {workflow.phase !== 'idle' && (
          <div className="mt-2.5 h-1.5 bg-slate-100 rounded-full overflow-hidden">
            <div className={`h-full rounded-full transition-all duration-700 ease-out ${
              workflow.phase === 'done' ? 'bg-emerald-500' :
              workflow.phase === 'error' ? 'bg-red-400' : 'bg-sky-500'
            }`} style={{ width: `${workflow.overallProgress}%` }} />
          </div>
        )}
        {workflow.query && (
          <div className="mt-2.5 px-3 py-2 bg-slate-50 border border-slate-100 rounded-lg">
            <p className="text-[10px] text-slate-500 font-medium mb-0.5">Query</p>
            <p className="text-xs text-slate-700 leading-relaxed">{workflow.query}</p>
          </div>
        )}
      </div>

      {/* Timeline */}
      <div className="flex-1 overflow-y-auto px-4 py-4 min-h-0">
        {workflow.agents.map((agent, idx) => (
          <AgentTimelineCard
            key={agent.id}
            agent={agent}
            isLast={idx === workflow.agents.length - 1}
            expanded={!!expandedAgents[agent.id]}
            onToggle={() => toggleExpand(agent.id)}
            onPause={handlePause}
            onRetry={handleRetry}
          />
        ))}
      </div>

      {/* Debug Toolbar */}
      {!externalWorkflow && (
        <div className="flex-shrink-0 border-t border-slate-200 bg-white">
          <button onClick={() => setShowDebug(!showDebug)}
            className="w-full px-4 py-2 text-[11px] font-semibold text-slate-400 hover:text-slate-600 flex items-center justify-center gap-1.5 transition-colors">
            <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
            {showDebug ? 'Hide' : 'Show'} Debug Controls
          </button>
          {showDebug && (
            <div className="px-4 pb-3">
              <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-2">Switch Mock Scenario</p>
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(MOCK_SCENARIOS).map(([key, scenario]) => (
                  <button key={key} onClick={() => setMockScenario(key)}
                    className={`px-2.5 py-1 text-[11px] font-semibold rounded-lg transition-colors ${
                      mockScenario === key ? 'bg-slate-900 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                    }`}>
                    {scenario.label}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
