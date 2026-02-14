import React, { useState, useEffect, useRef } from 'react';
import { WorkflowState, WorkflowPhase, AgentStatus } from '../../workflowTypes';

/* ═══════════════════════════════════════════════════════════════════════════
   CONSTANTS
   ═══════════════════════════════════════════════════════════════════════════ */

const STATUS_CONFIG: Record<
  AgentStatus['status'],
  { label: string; bg: string; text: string; dot: string; ring: string; lineDone: boolean }
> = {
  idle:      { label: 'Idle',       bg: 'bg-slate-800',        text: 'text-slate-500',   dot: 'bg-slate-600',    ring: 'ring-slate-700',   lineDone: false },
  waiting:   { label: 'Waiting',    bg: 'bg-amber-900/30',     text: 'text-amber-400',   dot: 'bg-amber-500',    ring: 'ring-amber-700',   lineDone: false },
  running:   { label: 'Running',    bg: 'bg-sky-900/30',       text: 'text-sky-400',     dot: 'bg-sky-500',      ring: 'ring-sky-600',     lineDone: false },
  completed: { label: 'Completed',  bg: 'bg-emerald-900/30',   text: 'text-emerald-400', dot: 'bg-emerald-500',  ring: 'ring-emerald-600', lineDone: true  },
  error:     { label: 'Error',      bg: 'bg-red-900/30',       text: 'text-red-400',     dot: 'bg-red-500',      ring: 'ring-red-600',     lineDone: false },
};

const PHASE_LABELS: Record<WorkflowPhase, string> = {
  idle:           'Waiting for query',
  classifying:    'Classifying intent...',
  planning:       'Planning tasks...',
  validating:     'Validating plan...',
  preprocessing:  'Preprocessing data...',
  executing:      'Executing analysis...',
  researching:    'Researching literature...',
  done:           'Workflow complete',
  error:          'Workflow error',
};

/* ═══════════════════════════════════════════════════════════════════════════
   UTILITY
   ═══════════════════════════════════════════════════════════════════════════ */

function formatDuration(startMs: number | null, endMs: number | null): string {
  if (!startMs) return '\u2014';
  const elapsed = (endMs || Date.now()) - startMs;
  const sec = Math.floor(elapsed / 1000);
  if (sec < 60) return `${sec}s`;
  return `${Math.floor(sec / 60)}m ${sec % 60}s`;
}

/* ═══════════════════════════════════════════════════════════════════════════
   SUB-COMPONENTS
   ═══════════════════════════════════════════════════════════════════════════ */

const PulsingDot: React.FC<{ className: string }> = ({ className }) => (
  <span className="relative flex h-3 w-3">
    <span className={`absolute inline-flex h-full w-full rounded-full opacity-60 animate-ping ${className}`} />
    <span className={`relative inline-flex h-3 w-3 rounded-full ${className}`} />
  </span>
);

const TimelineNode: React.FC<{ status: AgentStatus['status'] }> = ({ status }) => {
  const cfg = STATUS_CONFIG[status];

  if (status === 'running') {
    return (
      <div className={`relative z-10 flex items-center justify-center w-8 h-8 rounded-full bg-slate-800 ring-2 ${cfg.ring} shadow-sm`}>
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
    <div className={`relative z-10 flex items-center justify-center w-8 h-8 rounded-full bg-slate-800 ring-2 ${cfg.ring} shadow-sm`}>
      <span className={`w-2.5 h-2.5 rounded-full ${cfg.dot}`} />
    </div>
  );
};

interface AgentTimelineCardProps {
  agent: AgentStatus;
  isLast: boolean;
  expanded: boolean;
  onToggle: () => void;
}

const AgentTimelineCard: React.FC<AgentTimelineCardProps> = ({
  agent,
  isLast,
  expanded,
  onToggle,
}) => {
  const cfg = STATUS_CONFIG[agent.status];
  const messagesEndRef = useRef<HTMLDivElement>(null);

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
          <div
            className={`w-0.5 flex-1 mt-1 transition-colors duration-500 ${
              cfg.lineDone ? 'bg-emerald-700' : 'bg-slate-700'
            }`}
          />
        )}
      </div>

      {/* Card */}
      <div
        className={`flex-1 mb-4 rounded-xl border transition-all duration-200 overflow-hidden ${
          agent.status === 'running'
            ? 'border-sky-700/50 bg-sky-950/40'
            : agent.status === 'error'
            ? 'border-red-700/50 bg-red-950/30'
            : agent.status === 'completed'
            ? 'border-emerald-700/50 bg-emerald-950/20'
            : 'border-slate-700/50 bg-slate-800/40'
        }`}
      >
        {/* Header */}
        <button
          onClick={onToggle}
          className="w-full flex items-center justify-between px-3 py-2.5 text-left group"
        >
          <div className="flex items-center gap-2.5 min-w-0">
            <span className="text-base flex-shrink-0">{agent.icon}</span>
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs font-semibold text-slate-200">
                  {agent.name}
                </span>
                <span
                  className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[9px] font-bold uppercase tracking-wider ${cfg.bg} ${cfg.text}`}
                >
                  {cfg.label}
                </span>
              </div>
              <p className="text-[10px] text-slate-500 mt-0.5 truncate max-w-[240px]">
                {agent.currentStep || agent.role}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1.5 flex-shrink-0 ml-2">
            {agent.startTime && (
              <span className="text-[9px] font-mono text-slate-500 bg-slate-800 px-1 py-0.5 rounded">
                {formatDuration(agent.startTime, agent.endTime)}
              </span>
            )}
            <span className="text-[9px] font-mono text-slate-500 bg-slate-800 px-1 py-0.5 rounded hidden sm:inline">
              {agent.model}
            </span>
            <svg
              className={`w-3.5 h-3.5 text-slate-500 transition-transform duration-200 ${
                expanded ? 'rotate-180' : ''
              }`}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
            </svg>
          </div>
        </button>

        {/* Expanded detail */}
        {expanded && (
          <div className="px-3 pb-3 border-t border-slate-700/50">
            <div className="flex items-center gap-2.5 mt-2 mb-2 text-[10px] text-slate-500">
              <span>
                Model: <span className="font-mono text-slate-400">{agent.model}</span>
              </span>
              {agent.startTime && (
                <>
                  <span className="text-slate-700">|</span>
                  <span>
                    Duration:{' '}
                    <span className="font-mono text-slate-400">
                      {formatDuration(agent.startTime, agent.endTime)}
                    </span>
                  </span>
                </>
              )}
            </div>

            {agent.error && (
              <div className="mb-2 flex items-start gap-2 p-2 bg-red-950/40 border border-red-800/50 rounded-lg text-[10px] text-red-400">
                <svg className="w-3 h-3 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                  <path
                    fillRule="evenodd"
                    d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                    clipRule="evenodd"
                  />
                </svg>
                <span className="font-mono break-all">{agent.error}</span>
              </div>
            )}

            {agent.messages.length > 0 && (
              <div className="bg-slate-950 rounded-lg p-2 max-h-32 overflow-y-auto font-mono text-[10px] leading-relaxed custom-scrollbar">
                {agent.messages.map((msg, i) => (
                  <div key={i} className="flex gap-1.5">
                    <span className="text-slate-700 select-none flex-shrink-0">
                      {String(i + 1).padStart(2, '0')}
                    </span>
                    <span
                      className={
                        msg.startsWith('ERROR')
                          ? 'text-red-400'
                          : msg.startsWith('WARNING')
                          ? 'text-amber-400'
                          : 'text-emerald-400'
                      }
                    >
                      {msg}
                    </span>
                  </div>
                ))}
                <div ref={messagesEndRef} />
              </div>
            )}

            {agent.status === 'completed' && (
              <div className="mt-2">
                <span className="text-[10px] text-emerald-500 font-medium flex items-center gap-1">
                  <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                  </svg>
                  Finished
                </span>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

/* ═══════════════════════════════════════════════════════════════════════════
   MAIN COMPONENT
   ═══════════════════════════════════════════════════════════════════════════ */

interface AgentProgressPanelProps {
  workflow: WorkflowState;
}

const AgentProgressPanel: React.FC<AgentProgressPanelProps> = ({ workflow }) => {
  const [expandedAgents, setExpandedAgents] = useState<Record<string, boolean>>({});

  const toggleExpand = (agentId: string) => {
    setExpandedAgents((prev) => ({ ...prev, [agentId]: !prev[agentId] }));
  };

  // Auto-expand running or errored agents
  useEffect(() => {
    const autoExpand: Record<string, boolean> = {};
    workflow.agents.forEach((a) => {
      if (a.status === 'running' || a.status === 'error') {
        autoExpand[a.id] = true;
      }
    });
    setExpandedAgents((prev) => ({ ...prev, ...autoExpand }));
  }, [workflow.phase]);

  const completedCount = workflow.agents.filter((a) => a.status === 'completed').length;
  const totalCount = workflow.agents.length;

  // Only show agents that have been activated
  const visibleAgents = workflow.agents.filter((a) => a.status !== 'idle');

  return (
    <div className="flex flex-col h-full min-h-0 bg-slate-900 overflow-hidden">
      {/* Header */}
      <div className="flex-shrink-0 px-4 py-3 border-b border-slate-800">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div>
              <h3 className="text-sm font-semibold text-slate-200">Agent Workflow</h3>
              <p className="text-[10px] text-slate-500 mt-0.5">
                {PHASE_LABELS[workflow.phase]}
                {workflow.phase !== 'idle' && ` \u2014 ${completedCount}/${totalCount} agents`}
              </p>
            </div>
          </div>
          {workflow.phase !== 'idle' && (
            <span
              className={`text-[10px] font-bold px-2 py-0.5 rounded-md ${
                workflow.phase === 'done'
                  ? 'bg-emerald-900/50 text-emerald-400'
                  : workflow.phase === 'error'
                  ? 'bg-red-900/50 text-red-400'
                  : 'bg-sky-900/50 text-sky-400'
              }`}
            >
              {workflow.overallProgress}%
            </span>
          )}
        </div>
        {workflow.phase !== 'idle' && (
          <div className="mt-2 h-1 bg-slate-800 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-700 ease-out ${
                workflow.phase === 'done'
                  ? 'bg-emerald-500'
                  : workflow.phase === 'error'
                  ? 'bg-red-500'
                  : 'bg-sky-500'
              }`}
              style={{ width: `${workflow.overallProgress}%` }}
            />
          </div>
        )}
        {workflow.query && (
          <div className="mt-2 px-3 py-2 bg-slate-800/50 border border-slate-700/50 rounded-lg">
            <p className="text-[9px] text-slate-500 font-medium mb-0.5">Query</p>
            <p className="text-[11px] text-slate-300 leading-relaxed">{workflow.query}</p>
          </div>
        )}
      </div>

      {/* Timeline */}
      <div className="flex-1 overflow-y-auto px-4 py-4 min-h-0 custom-scrollbar">
        {visibleAgents.length === 0 ? (
          <div className="flex items-center justify-center h-full text-xs text-slate-600">
            Initializing agents...
          </div>
        ) : (
          visibleAgents.map((agent, idx) => (
            <AgentTimelineCard
              key={agent.id}
              agent={agent}
              isLast={idx === visibleAgents.length - 1}
              expanded={!!expandedAgents[agent.id]}
              onToggle={() => toggleExpand(agent.id)}
            />
          ))
        )}
      </div>
    </div>
  );
};

export default AgentProgressPanel;
