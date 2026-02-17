import React, { useState, useEffect, useRef } from 'react';
import { WorkflowRecord, WorkflowPhase } from '../../workflowTypes';
import { ChatMessage, AgentType } from '../../types';
import { AGENT_COLORS } from '../../constants';
import {
  GitFork, BrainCircuit, Settings, ShieldCheck, FileCog,
  Terminal, Microscope, Bot, RotateCcw, Check, X, ChevronDown,
} from 'lucide-react';

/* ═══════════════════════════════════════════════════════════════════════════
   TYPES & HELPERS
   ═══════════════════════════════════════════════════════════════════════════ */

interface ThinkingOverlayProps {
  record: WorkflowRecord;
  isActive: boolean;
  /** Messages that belong to this workflow (already sliced by parent) */
  workflowMessages: ChatMessage[];
  highlightedMessageId: string | null;
  /** Set by ChatArea when user clicked a bubble — consumed on expand to highlight the agent */
  pendingHighlightId: string | null;
  onRestartStep: (messageId: string, newParams: any) => void;
  onRequestExpand: () => void;
  onRequestCollapse: () => void;
  isExpanded: boolean;
  /** Whether the collapsed bar itself should pulse (user clicked a bubble that belongs here) */
  isBarHighlighted: boolean;
  /** Live elapsed seconds (only meaningful when isActive) */
  elapsedSeconds: number;
}

const AGENT_ICON: Record<string, React.ReactNode> = {
  [AgentType.ORCHESTRATOR]: <GitFork className="w-3.5 h-3.5" />,
  [AgentType.NEURO_PLANNER]: <BrainCircuit className="w-3.5 h-3.5" />,
  [AgentType.GENERAL_PLANNER]: <Settings className="w-3.5 h-3.5" />,
  [AgentType.PLANNER]: <BrainCircuit className="w-3.5 h-3.5" />,
  [AgentType.PLAN_VALIDATOR]: <ShieldCheck className="w-3.5 h-3.5" />,
  [AgentType.PREPROCESSOR]: <FileCog className="w-3.5 h-3.5" />,
  [AgentType.EXECUTOR]: <Terminal className="w-3.5 h-3.5" />,
  [AgentType.RESEARCHER]: <Microscope className="w-3.5 h-3.5" />,
  [AgentType.SYSTEM]: <Bot className="w-3.5 h-3.5" />,
};

const AGENT_LABEL: Record<string, string> = {
  [AgentType.ORCHESTRATOR]: 'Orchestrator',
  [AgentType.NEURO_PLANNER]: 'Neuro Planner',
  [AgentType.GENERAL_PLANNER]: 'General Planner',
  [AgentType.PLAN_VALIDATOR]: 'Plan Validator',
  [AgentType.PREPROCESSOR]: 'Preprocessor',
  [AgentType.EXECUTOR]: 'Executor',
  [AgentType.RESEARCHER]: 'Researcher',
  [AgentType.SYSTEM]: 'System',
};

const NODE_THEME: Record<string, { border: string; header: string; icon: string }> = {
  [AgentType.ORCHESTRATOR]:    { border: 'border-fuchsia-700/60',  header: 'bg-fuchsia-900/40',  icon: 'text-fuchsia-400' },
  [AgentType.NEURO_PLANNER]:   { border: 'border-indigo-700/60',   header: 'bg-indigo-900/40',   icon: 'text-indigo-400' },
  [AgentType.GENERAL_PLANNER]: { border: 'border-blue-700/60',     header: 'bg-blue-900/40',     icon: 'text-blue-400' },
  [AgentType.PLAN_VALIDATOR]:  { border: 'border-rose-700/60',     header: 'bg-rose-900/40',     icon: 'text-rose-400' },
  [AgentType.PREPROCESSOR]:    { border: 'border-teal-700/60',     header: 'bg-teal-900/40',     icon: 'text-teal-400' },
  [AgentType.EXECUTOR]:        { border: 'border-emerald-700/60',  header: 'bg-emerald-900/40',  icon: 'text-emerald-400' },
  [AgentType.RESEARCHER]:      { border: 'border-purple-700/60',   header: 'bg-purple-900/40',   icon: 'text-purple-400' },
  [AgentType.SYSTEM]:          { border: 'border-slate-700/60',    header: 'bg-slate-800/40',    icon: 'text-slate-400' },
};

const PHASE_LABELS: Record<string, string> = {
  idle: 'Waiting', classifying: 'Classifying intent...', planning: 'Creating plan...',
  validating: 'Validating plan...', executing: 'Executing...', researching: 'Generating report...',
  done: 'Complete', error: 'Error',
};

function formatTime(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

/* ═══════════════════════════════════════════════════════════════════════════
   FLOW NODE
   ═══════════════════════════════════════════════════════════════════════════ */

interface FlowNodeProps {
  message: ChatMessage;
  isLast: boolean;
  highlightedMessageId: string | null;
  onRestart?: (messageId: string, newParams: any) => void;
  nodeRef?: (el: HTMLDivElement | null) => void;
}

const FlowNode: React.FC<FlowNodeProps> = ({ message, isLast, highlightedMessageId, onRestart, nodeRef }) => {
  const [expanded, setExpanded] = useState(true);
  const theme = NODE_THEME[message.role] || NODE_THEME[AgentType.SYSTEM];
  const label = AGENT_LABEL[message.role] || message.role;
  const icon = AGENT_ICON[message.role];
  const isHighlighted = message.id === highlightedMessageId;
  const [isPulsing, setIsPulsing] = useState(false);

  useEffect(() => {
    if (isHighlighted) {
      setIsPulsing(true);
      const timer = setTimeout(() => setIsPulsing(false), 2000);
      return () => clearTimeout(timer);
    }
  }, [isHighlighted]);

  const isPlanner = message.role === AgentType.NEURO_PLANNER || message.role === AgentType.GENERAL_PLANNER;
  const isExecutor = message.role === AgentType.EXECUTOR;
  const canEdit = onRestart && (
    (isExecutor && message.metadata?.params) ||
    (isPlanner && message.metadata?.plan)
  );

  const [isEditing, setIsEditing] = useState(false);
  const [editParams, setEditParams] = useState(() => {
    if (isExecutor && message.metadata?.params) return JSON.stringify(message.metadata.params, null, 2);
    if (isPlanner && message.metadata?.plan) return JSON.stringify(message.metadata.plan, null, 2);
    return '';
  });

  const handleRun = () => {
    try {
      const parsed = JSON.parse(editParams);
      if (onRestart) onRestart(message.id, parsed);
      setIsEditing(false);
    } catch {
      alert('Invalid JSON format');
    }
  };

  return (
    <div ref={nodeRef} className="flex flex-col items-center">
      <div
        className={`w-full max-w-2xl border rounded-lg overflow-hidden transition-all duration-300 ${theme.border} ${
          isHighlighted
            ? `ring-2 ring-indigo-400 shadow-lg shadow-indigo-500/20 ${isPulsing ? 'animate-glow-flash' : ''}`
            : ''
        }`}
      >
        {isHighlighted && isPulsing && (
          <div className="flex items-center gap-2 px-3 py-1.5 bg-indigo-600/20 border-b border-indigo-500/30">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75 animate-ping" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-indigo-500" />
            </span>
            <span className="text-[10px] font-semibold text-indigo-300 uppercase tracking-wider">Source Agent</span>
          </div>
        )}

        <button onClick={() => setExpanded(!expanded)} className={`w-full flex items-center justify-between px-3 py-2 ${theme.header}`}>
          <div className="flex items-center gap-2">
            <span className={theme.icon}>{icon}</span>
            <span className="text-xs font-bold text-slate-200">{label}</span>
            {message.metadata?.model && (
              <span className="text-[9px] font-mono text-slate-500 bg-slate-900/50 px-1.5 py-0.5 rounded">{message.metadata.model}</span>
            )}
            <span className="text-[9px] text-slate-600">
              {new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
            </span>
          </div>
          <ChevronDown className={`w-3.5 h-3.5 text-slate-500 transition-transform ${expanded ? 'rotate-180' : ''}`} />
        </button>

        {expanded && (
          <div className="px-3 py-2.5 bg-slate-900/60">
            <pre className="text-xs text-slate-300 leading-relaxed whitespace-pre-wrap font-sans">{message.content}</pre>

            {canEdit && !isEditing && (
              <div className="mt-2 pt-2 border-t border-slate-700/50 flex justify-end">
                <button
                  onClick={(e) => { e.stopPropagation(); setIsEditing(true); }}
                  className="flex items-center gap-1 text-[10px] text-indigo-400 hover:text-indigo-300 bg-slate-800/60 px-2 py-1 rounded"
                >
                  <RotateCcw className="w-3 h-3" />
                  {isPlanner ? 'Edit Plan & Restart' : 'Edit & Restart Step'}
                </button>
              </div>
            )}

            {isEditing && (
              <div className="mt-2 bg-slate-950/50 rounded p-2 border border-slate-700/50">
                <p className="text-[10px] text-slate-500 mb-1">{isPlanner ? 'Edit Plan (JSON):' : 'Edit Tool Parameters (JSON):'}</p>
                <textarea
                  value={editParams}
                  onChange={(e) => setEditParams(e.target.value)}
                  onClick={(e) => e.stopPropagation()}
                  className="w-full h-40 bg-slate-900 text-[10px] font-mono text-slate-300 p-2 rounded border border-slate-700 focus:outline-none focus:border-indigo-500"
                />
                <div className="flex justify-end gap-2 mt-2">
                  <button onClick={() => setIsEditing(false)} className="p-1 text-slate-400 hover:text-slate-200"><X className="w-3.5 h-3.5" /></button>
                  <button onClick={handleRun} className="flex items-center gap-1 bg-indigo-600 hover:bg-indigo-500 text-white text-[10px] px-2.5 py-1 rounded">
                    <Check className="w-3 h-3" /> {isPlanner ? 'Update Plan' : 'Run'}
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {!isLast && (
        <div className="flex flex-col items-center py-1">
          <div className="w-0.5 h-4 bg-slate-700" />
          <svg className="w-3 h-2 text-slate-600" viewBox="0 0 12 8" fill="currentColor"><path d="M6 8L0 0h12z" /></svg>
        </div>
      )}
    </div>
  );
};

/* ═══════════════════════════════════════════════════════════════════════════
   MAIN COMPONENT
   ═══════════════════════════════════════════════════════════════════════════ */

const ThinkingOverlay: React.FC<ThinkingOverlayProps> = ({
  record, isActive, workflowMessages, highlightedMessageId, pendingHighlightId,
  onRestartStep, onRequestExpand, onRequestCollapse, isExpanded, isBarHighlighted, elapsedSeconds,
}) => {
  const scrollRef = useRef<HTMLDivElement>(null);
  const nodeRefs = useRef<{ [key: string]: HTMLDivElement | null }>({});

  // The effective highlight ID inside the overlay:
  // Use pendingHighlightId if set (user navigated from a bubble), otherwise use highlightedMessageId
  const effectiveHighlightId = pendingHighlightId || highlightedMessageId;

  // Inject CSS animation
  useEffect(() => {
    const styleId = 'thinking-overlay-styles';
    if (document.getElementById(styleId)) return;
    const style = document.createElement('style');
    style.id = styleId;
    style.textContent = `
      @keyframes glow-flash {
        0% { box-shadow: 0 0 0 0 rgba(99, 102, 241, 0); }
        30% { box-shadow: 0 0 20px 6px rgba(99, 102, 241, 0.4); }
        100% { box-shadow: 0 0 0 0 rgba(99, 102, 241, 0); }
      }
      .animate-glow-flash {
        animation: glow-flash 1.2s ease-out 1 forwards;
      }
    `;
    document.head.appendChild(style);
  }, []);

  // Auto-scroll when new messages arrive
  useEffect(() => {
    if (isExpanded && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [workflowMessages.length, isExpanded]);

  // Scroll to highlighted node
  useEffect(() => {
    if (!isExpanded || !effectiveHighlightId) return;
    if (nodeRefs.current[effectiveHighlightId]) {
      setTimeout(() => {
        nodeRefs.current[effectiveHighlightId]?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }, 100);
    }
  }, [effectiveHighlightId, isExpanded]);

  const queryMessages = workflowMessages.filter((m) => m.role !== AgentType.USER);
  const isComplete = record.phase === 'done' || record.phase === 'error';
  const displaySeconds = isActive ? elapsedSeconds : record.elapsedSeconds;

  // ── Expanded: full overlay ──
  if (isExpanded) {
    const phaseOrder: WorkflowPhase[] = ['classifying', 'planning', 'validating', 'executing', 'researching'];
    const currentIdx = phaseOrder.indexOf(record.phase);

    return (
      <div className="absolute inset-0 z-20 flex flex-col bg-slate-950">
        {/* Header */}
        <div className="flex-shrink-0 px-5 py-4 bg-slate-900 border-b border-slate-800">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-3">
              {isActive ? (
                <span className="relative flex h-2.5 w-2.5">
                  <span className="absolute inline-flex h-full w-full rounded-full bg-sky-400 opacity-75 animate-ping" />
                  <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-sky-500" />
                </span>
              ) : record.phase === 'done' ? (
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
              ) : (
                <span className="w-2.5 h-2.5 rounded-full bg-red-500" />
              )}
              <span className="text-sm font-semibold text-slate-200">Thinking Process</span>
              <span className="text-xs font-mono text-slate-500 bg-slate-800 px-2 py-0.5 rounded">{formatTime(displaySeconds)}</span>
              <span className={`text-xs font-bold px-2 py-0.5 rounded ${
                record.phase === 'done' ? 'bg-emerald-900/50 text-emerald-400'
                : record.phase === 'error' ? 'bg-red-900/50 text-red-400'
                : 'bg-sky-900/50 text-sky-400'
              }`}>{record.overallProgress}%</span>
            </div>
            <button onClick={onRequestCollapse} className="p-1.5 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition-colors">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* Progress bar */}
          <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden mb-2">
            <div className={`h-full rounded-full transition-all duration-700 ease-out ${
              record.phase === 'done' ? 'bg-emerald-500' : record.phase === 'error' ? 'bg-red-500' : 'bg-sky-500'
            }`} style={{ width: `${record.overallProgress}%` }} />
          </div>
          <div className="flex justify-between">
            {phaseOrder.map((phase, idx) => {
              const names: Record<string, string> = {
                classifying: 'Orchestrator', planning: 'Planner',
                validating: 'Validator', executing: 'Executor', researching: 'Researcher',
              };
              const isDone = record.phase === 'done' || idx < currentIdx;
              const isCurrent = phase === record.phase;
              return (
                <span key={phase} className={`text-[9px] font-medium ${isDone ? 'text-emerald-500' : isCurrent ? 'text-sky-400' : 'text-slate-600'}`}>
                  {isDone ? '✓ ' : ''}{names[phase]}
                </span>
              );
            })}
          </div>

          {/* Query title */}
          <div className="mt-3 px-3 py-2 bg-slate-800/60 border border-slate-700/40 rounded-lg">
            <p className="text-[9px] text-slate-500 font-medium uppercase tracking-wider mb-0.5">Query</p>
            <p className="text-sm text-slate-200 leading-relaxed">{record.query}</p>
          </div>
        </div>

        {/* Flowchart body */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-5 py-5 custom-scrollbar">
          <div className="flex flex-col items-center">
            {queryMessages.map((msg, idx) => (
              <FlowNode
                key={msg.id}
                message={msg}
                isLast={idx === queryMessages.length - 1 && !isActive}
                highlightedMessageId={effectiveHighlightId}
                onRestart={onRestartStep}
                nodeRef={(el) => { nodeRefs.current[msg.id] = el; }}
              />
            ))}
            {isActive && (
              <div className="flex flex-col items-center pt-2">
                <div className="w-0.5 h-4 bg-slate-700" />
                <div className="flex items-center gap-2 px-4 py-2 rounded-full bg-slate-800/60 border border-sky-700/30">
                  <span className="relative flex h-2 w-2">
                    <span className="absolute inline-flex h-full w-full rounded-full bg-sky-400 opacity-75 animate-ping" />
                    <span className="relative inline-flex h-2 w-2 rounded-full bg-sky-500" />
                  </span>
                  <span className="text-[10px] text-sky-400 font-medium">{PHASE_LABELS[record.phase] || 'Processing...'}</span>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Completion banner */}
        {isComplete && (
          <div className={`flex-shrink-0 flex items-center justify-between px-5 py-3 border-t ${
            record.phase === 'done' ? 'border-emerald-800/50 bg-emerald-950/30' : 'border-red-800/50 bg-red-950/30'
          }`}>
            <div className="flex items-center gap-2.5">
              {record.phase === 'done' ? (
                <>
                  <svg className="w-4 h-4 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                  </svg>
                  <span className="text-sm font-medium text-emerald-300">Thinking complete</span>
                  <span className="text-xs text-emerald-500/70">— took {formatTime(displaySeconds)}</span>
                </>
              ) : (
                <>
                  <svg className="w-4 h-4 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                  <span className="text-sm font-medium text-red-300">Workflow failed</span>
                </>
              )}
            </div>
            <button onClick={onRequestCollapse} className={`text-xs font-semibold px-3 py-1.5 rounded-lg transition-colors ${
              record.phase === 'done' ? 'bg-emerald-800/40 text-emerald-300 hover:bg-emerald-800/60' : 'bg-red-800/40 text-red-300 hover:bg-red-800/60'
            }`}>View results</button>
          </div>
        )}
      </div>
    );
  }

  // ── Collapsed bar ──
  if (isActive) {
    return (
      <button onClick={onRequestExpand}
        className={`mx-3 mb-2 flex items-center gap-3 px-4 py-2.5 rounded-xl bg-slate-800/80 border transition-all group cursor-pointer ${
          isBarHighlighted
            ? 'border-indigo-500 ring-2 ring-indigo-400/50 animate-glow-flash'
            : 'border-slate-700/50 hover:border-sky-600/50 hover:bg-slate-800'
        }`}>
        <span className="relative flex h-2.5 w-2.5 flex-shrink-0">
          <span className="absolute inline-flex h-full w-full rounded-full bg-sky-400 opacity-75 animate-ping" />
          <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-sky-500" />
        </span>
        <span className="text-xs text-slate-300 font-medium">{PHASE_LABELS[record.phase] || 'Agents working...'}</span>
        <span className="text-xs font-mono text-slate-500">{formatTime(displaySeconds)}</span>
        {record.overallProgress > 0 && (
          <div className="flex-1 max-w-[120px] h-1 bg-slate-700 rounded-full overflow-hidden">
            <div className="h-full bg-sky-500 rounded-full transition-all duration-500" style={{ width: `${record.overallProgress}%` }} />
          </div>
        )}
        {isBarHighlighted && (
          <span className="text-[9px] font-semibold text-indigo-300 animate-pulse">← Click to view agent</span>
        )}
        <svg className="w-3.5 h-3.5 text-slate-500 group-hover:text-sky-400 transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>
    );
  }

  // Completed bar
  return (
    <button onClick={onRequestExpand}
      className={`mx-3 mb-2 flex items-center gap-2.5 px-4 py-2 rounded-xl transition-all group cursor-pointer ${
        isBarHighlighted
          ? 'bg-slate-800/70 border border-indigo-500 ring-2 ring-indigo-400/50 animate-glow-flash'
          : 'bg-slate-800/50 border border-slate-700/30 hover:border-emerald-600/40 hover:bg-slate-800/70'
      }`}>
      <span className={`w-2 h-2 rounded-full flex-shrink-0 ${record.phase === 'done' ? 'bg-emerald-500' : 'bg-red-500'}`} />
      <span className="text-xs text-slate-400 group-hover:text-slate-300 transition-colors">
        Thought for {formatTime(displaySeconds)}
      </span>
      <span className="text-[10px] font-medium text-slate-500 group-hover:text-emerald-400 transition-colors">— View thinking process</span>
      {isBarHighlighted && (
        <span className="text-[9px] font-semibold text-indigo-300 animate-pulse">← Click to view agent</span>
      )}
      <svg className="w-3 h-3 text-slate-600 group-hover:text-emerald-400 transition-colors ml-auto" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
      </svg>
    </button>
  );
};

export default ThinkingOverlay;