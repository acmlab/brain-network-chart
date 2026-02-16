import React, { useState, useEffect, useRef } from 'react';
import { WorkflowState } from '../../workflowTypes';
import AgentProgressPanel from './AgentProgressPanel';

interface ThinkingOverlayProps {
  workflow: WorkflowState;
  isProcessing: boolean;
}

const ThinkingOverlay: React.FC<ThinkingOverlayProps> = ({ workflow, isProcessing }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const startTimeRef = useRef<number | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Start/stop the elapsed timer based on processing state
  useEffect(() => {
    if (isProcessing && workflow.phase !== 'idle') {
      if (!startTimeRef.current) {
        startTimeRef.current = Date.now();
      }
      timerRef.current = setInterval(() => {
        if (startTimeRef.current) {
          setElapsedSeconds(Math.floor((Date.now() - startTimeRef.current) / 1000));
        }
      }, 1000);
    } else if (!isProcessing && startTimeRef.current) {
      // Stop timer but do NOT auto-collapse
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    }

    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
    };
  }, [isProcessing, workflow.phase]);

  // Reset timer and auto-expand on new query
  useEffect(() => {
    if (workflow.phase === 'classifying') {
      startTimeRef.current = Date.now();
      setElapsedSeconds(0);
      // setIsExpanded(true);
    }
  }, [workflow.phase]);

  const formatTime = (seconds: number): string => {
    if (seconds < 60) return `${seconds}s`;
    return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  };

  const isActive = isProcessing && workflow.phase !== 'idle';
  const isComplete = !isProcessing && (workflow.phase === 'done' || workflow.phase === 'error');
  const hasWorkflow = workflow.phase !== 'idle';

  // Nothing to show
  if (!hasWorkflow) return null;

  // Expanded: full overlay
  if (isExpanded) {
    return (
      <div className="absolute inset-0 z-20 flex flex-col bg-slate-900">
        {/* Header bar with close button */}
        <div className="flex-shrink-0 flex items-center justify-between px-4 py-3 bg-slate-800 border-b border-slate-700">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              {isActive ? (
                <span className="relative flex h-2.5 w-2.5">
                  <span className="absolute inline-flex h-full w-full rounded-full bg-sky-400 opacity-75 animate-ping" />
                  <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-sky-500" />
                </span>
              ) : isComplete && workflow.phase === 'done' ? (
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
              ) : (
                <span className="w-2.5 h-2.5 rounded-full bg-red-500" />
              )}
              <span className="text-sm font-semibold text-slate-200">
                {isActive ? 'Agents Working' : 'Thinking Process'}
              </span>
            </div>
            <span className="text-xs font-mono text-slate-400 bg-slate-700 px-2 py-0.5 rounded">
              {formatTime(elapsedSeconds)}
            </span>
            {workflow.overallProgress > 0 && (
              <span className={`text-xs font-bold px-2 py-0.5 rounded ${
                isComplete && workflow.phase === 'done'
                  ? 'bg-emerald-900/50 text-emerald-400'
                  : isComplete && workflow.phase === 'error'
                  ? 'bg-red-900/50 text-red-400'
                  : 'bg-sky-900/50 text-sky-400'
              }`}>
                {workflow.overallProgress}%
              </span>
            )}
          </div>
          <button
            onClick={() => setIsExpanded(false)}
            className="p-1.5 rounded-lg hover:bg-slate-700 text-slate-400 hover:text-slate-200 transition-colors"
            title="Close thinking panel"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* AgentProgressPanel fills the rest */}
        <div className="flex-1 min-h-0 overflow-hidden">
          <AgentProgressPanel workflow={workflow} />
        </div>

        {/* Completion banner at the bottom */}
        {isComplete && (
          <div className={`flex-shrink-0 flex items-center justify-between px-4 py-3 border-t ${
            workflow.phase === 'done'
              ? 'border-emerald-800/50 bg-emerald-950/30'
              : 'border-red-800/50 bg-red-950/30'
          }`}>
            <div className="flex items-center gap-2.5">
              {workflow.phase === 'done' ? (
                <>
                  <svg className="w-4 h-4 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                  </svg>
                  <span className="text-sm font-medium text-emerald-300">
                    Thinking complete
                  </span>
                  <span className="text-xs text-emerald-500/70">
                    — took {formatTime(elapsedSeconds)}
                  </span>
                </>
              ) : (
                <>
                  <svg className="w-4 h-4 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                  <span className="text-sm font-medium text-red-300">
                    Workflow failed
                  </span>
                </>
              )}
            </div>
            <button
              onClick={() => setIsExpanded(false)}
              className={`text-xs font-semibold px-3 py-1.5 rounded-lg transition-colors ${
                workflow.phase === 'done'
                  ? 'bg-emerald-800/40 text-emerald-300 hover:bg-emerald-800/60'
                  : 'bg-red-800/40 text-red-300 hover:bg-red-800/60'
              }`}
            >
              View results
            </button>
          </div>
        )}
      </div>
    );
  }

  // Collapsed: inline bar
  if (isActive) {
    return (
      <button
        onClick={() => setIsExpanded(true)}
        className="mx-3 mb-2 flex items-center gap-3 px-4 py-2.5 rounded-xl bg-slate-800/80 border border-slate-700/50 hover:border-sky-600/50 hover:bg-slate-800 transition-all group cursor-pointer"
      >
        <span className="relative flex h-2.5 w-2.5 flex-shrink-0">
          <span className="absolute inline-flex h-full w-full rounded-full bg-sky-400 opacity-75 animate-ping" />
          <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-sky-500" />
        </span>
        <span className="text-xs text-slate-300 font-medium">
          Agents working...
        </span>
        <span className="text-xs font-mono text-slate-500">
          {formatTime(elapsedSeconds)}
        </span>
        {workflow.overallProgress > 0 && (
          <div className="flex-1 max-w-[120px] h-1 bg-slate-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-sky-500 rounded-full transition-all duration-500"
              style={{ width: `${workflow.overallProgress}%` }}
            />
          </div>
        )}
        <svg className="w-3.5 h-3.5 text-slate-500 group-hover:text-sky-400 transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>
    );
  }

  if (isComplete) {
    return (
      <button
        onClick={() => setIsExpanded(true)}
        className="mx-3 mb-2 flex items-center gap-2.5 px-4 py-2 rounded-xl bg-slate-800/50 border border-slate-700/30 hover:border-emerald-600/40 hover:bg-slate-800/70 transition-all group cursor-pointer"
      >
        <span className={`w-2 h-2 rounded-full flex-shrink-0 ${
          workflow.phase === 'done' ? 'bg-emerald-500' : 'bg-red-500'
        }`} />
        <span className="text-xs text-slate-400 group-hover:text-slate-300 transition-colors">
          Thought for {formatTime(elapsedSeconds)}
        </span>
        <span className={`text-[10px] font-medium transition-colors ${
          workflow.phase === 'done'
            ? 'text-slate-500 group-hover:text-emerald-400'
            : 'text-slate-500 group-hover:text-red-400'
        }`}>
          — View thinking process
        </span>
        <svg className="w-3 h-3 text-slate-600 group-hover:text-emerald-400 transition-colors ml-auto" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>
    );
  }

  return null;
};

export default ThinkingOverlay;
