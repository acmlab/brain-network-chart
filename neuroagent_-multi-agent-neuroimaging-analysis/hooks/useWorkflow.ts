import { useState, useCallback } from 'react';
import {
  WorkflowState,
  WorkflowPhase,
  createInitialWorkflow,
  PHASE_BASE_PROGRESS,
} from '../workflowTypes';

export function useWorkflow() {
  const [workflowState, setWorkflowState] = useState<WorkflowState>(
    createInitialWorkflow()
  );

  const update = useCallback((fn: (prev: WorkflowState) => WorkflowState) => {
    setWorkflowState((prev) => fn(prev));
  }, []);

  const startNewQuery = useCallback(
    (query: string, currentMessageCount: number) => {
      update(() => ({
        ...createInitialWorkflow(),
        query,
        phase: 'classifying' as WorkflowPhase,
        overallProgress: PHASE_BASE_PROGRESS.classifying,
        queryStartIndex: currentMessageCount,
      }));
    },
    [update]
  );

  const setPhase = useCallback(
    (phase: WorkflowPhase) => {
      update((s) => ({
        ...s,
        phase,
        overallProgress:
          phase === 'error'
            ? s.overallProgress
            : PHASE_BASE_PROGRESS[phase] ?? s.overallProgress,
      }));
    },
    [update]
  );

  const setExecutionProgress = useCallback(
    (done: number, total: number) => {
      update((s) => {
        if (s.phase !== 'executing' || total === 0) return s;
        const subProgress = Math.round((done / total) * 20);
        return {
          ...s,
          executionStepsDone: done,
          executionStepsTotal: total,
          overallProgress: 60 + subProgress,
        };
      });
    },
    [update]
  );

  const setProgress = useCallback(
    (progress: number) => {
      update((s) => ({ ...s, overallProgress: Math.min(100, progress) }));
    },
    [update]
  );

  const reset = useCallback(() => {
    update(() => createInitialWorkflow());
  }, [update]);

  return {
    workflowState,
    wf: {
      startNewQuery,
      setPhase,
      setExecutionProgress,
      setProgress,
      reset,
    },
  };
}
