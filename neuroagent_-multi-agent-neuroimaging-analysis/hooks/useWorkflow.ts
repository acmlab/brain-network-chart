import { useState, useCallback } from 'react';
import {
  WorkflowHistory,
  WorkflowRecord,
  WorkflowPhase,
  createInitialHistory,
  generateWorkflowId,
  PHASE_BASE_PROGRESS,
} from '../workflowTypes';

function updateActive(
  history: WorkflowHistory,
  patch: Partial<WorkflowRecord>
): WorkflowHistory {
  if (!history.activeId) return history;
  return {
    ...history,
    records: history.records.map((r) =>
      r.id === history.activeId ? { ...r, ...patch } : r
    ),
  };
}

export function useWorkflow() {
  const [history, setHistory] = useState<WorkflowHistory>(createInitialHistory());

  const update = useCallback(
    (fn: (prev: WorkflowHistory) => WorkflowHistory) => {
      setHistory((prev) => fn(prev));
    },
    []
  );

  /** Start a new query — creates a new WorkflowRecord */
  const startNewQuery = useCallback(
    (query: string, currentMessageCount: number): string => {
      const id = generateWorkflowId();
      update((h) => ({
        ...h,
        records: [
          ...h.records,
          {
            id,
            query,
            phase: 'classifying' as WorkflowPhase,
            overallProgress: PHASE_BASE_PROGRESS.classifying,
            startIndex: currentMessageCount,
            endIndex: -1,
            elapsedSeconds: 0,
          },
        ],
        activeId: id,
      }));
      return id;
    },
    [update]
  );

  /** Transition to a new phase */
  const setPhase = useCallback(
    (phase: WorkflowPhase) => {
      update((h) =>
        updateActive(h, {
          phase,
          overallProgress:
            phase === 'error'
              ? h.records.find((r) => r.id === h.activeId)?.overallProgress ?? 0
              : PHASE_BASE_PROGRESS[phase] ?? 0,
        })
      );
    },
    [update]
  );

  /** Update execution sub-progress (60-80% range) */
  const setExecutionProgress = useCallback(
    (done: number, total: number) => {
      update((h) => {
        const active = h.records.find((r) => r.id === h.activeId);
        if (!active || active.phase !== 'executing' || total === 0) return h;
        const subProgress = Math.round((done / total) * 20);
        return updateActive(h, { overallProgress: 60 + subProgress });
      });
    },
    [update]
  );

  /** Finalize a workflow: set endIndex and elapsed time */
  const finalize = useCallback(
    (currentMessageCount: number, elapsedSeconds: number) => {
      update((h) => {
        const updated = updateActive(h, {
          endIndex: currentMessageCount,
          elapsedSeconds,
        });
        return { ...updated, activeId: null };
      });
    },
    [update]
  );

  /** Truncate history: remove all workflows after a given workflow ID
   *  and return the startIndex of the truncated workflow so App can trim messages */
  const truncateAfter = useCallback(
    (workflowId: string): number => {
      let truncateStartIndex = -1;
      update((h) => {
        const idx = h.records.findIndex((r) => r.id === workflowId);
        if (idx === -1) return h;
        // The workflow being edited keeps its startIndex;
        // everything from that workflow's startIndex onward gets deleted
        truncateStartIndex = h.records[idx].startIndex;
        return {
          ...h,
          records: h.records.slice(0, idx),
          activeId: null,
        };
      });
      return truncateStartIndex;
    },
    [update]
  );

  /** Find which workflow a message belongs to */
  const findWorkflowForMessage = useCallback(
    (messageIndex: number): WorkflowRecord | null => {
      // Search in reverse (most recent first)
      for (let i = history.records.length - 1; i >= 0; i--) {
        const r = history.records[i];
        const end = r.endIndex === -1 ? Infinity : r.endIndex;
        if (messageIndex >= r.startIndex && messageIndex < end) {
          return r;
        }
      }
      return null;
    },
    [history.records]
  );

  return {
    history,
    wf: {
      startNewQuery,
      setPhase,
      setExecutionProgress,
      finalize,
      truncateAfter,
      findWorkflowForMessage,
    },
  };
}
