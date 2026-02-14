import { useState, useCallback, useRef } from 'react';
import {
  WorkflowState,
  WorkflowPhase,
  AgentStatus,
  createInitialWorkflow,
  createInitialAgents,
  PHASE_PROGRESS,
} from '../workflowTypes';

// Helper: update a single agent inside the workflow
function updateAgent(
  state: WorkflowState,
  agentId: string,
  patch: Partial<AgentStatus>
): WorkflowState {
  return {
    ...state,
    agents: state.agents.map((a) =>
      a.id === agentId ? { ...a, ...patch } : a
    ),
  };
}

/**
 * useWorkflow — manages the WorkflowState that drives AgentProgressPanel.
 *
 * Returns:
 *  - workflowState: current state (pass to <AgentProgressPanel workflow={workflowState} />)
 *  - wf: object with imperative methods to call from handleUserQuery / executePlanSteps
 */
export function useWorkflow() {
  const [workflowState, setWorkflowState] = useState<WorkflowState>(
    createInitialWorkflow()
  );

  // Use ref so async callbacks always read the latest state
  const stateRef = useRef(workflowState);
  const update = useCallback((fn: (prev: WorkflowState) => WorkflowState) => {
    setWorkflowState((prev) => {
      const next = fn(prev);
      stateRef.current = next;
      return next;
    });
  }, []);

  // ── Public API ──────────────────────────────────────────────────────────

  /** Reset everything for a new query */
  const startNewQuery = useCallback(
    (query: string) => {
      update(() => ({
        query,
        agents: createInitialAgents(),
        phase: 'classifying' as WorkflowPhase,
        overallProgress: PHASE_PROGRESS.classifying,
      }));
    },
    [update]
  );

  /** Mark an agent as running */
  const agentStart = useCallback(
    (agentId: string, currentStep: string, model?: string) => {
      update((s) => {
        let patched = updateAgent(s, agentId, {
          status: 'running',
          currentStep,
          startTime: Date.now(),
          endTime: null,
          error: null,
          ...(model ? { model } : {}),
        });
        return patched;
      });
    },
    [update]
  );

  /** Append a log message to an agent */
  const agentLog = useCallback(
    (agentId: string, message: string) => {
      update((s) => {
        const agent = s.agents.find((a) => a.id === agentId);
        if (!agent) return s;
        return updateAgent(s, agentId, {
          messages: [...agent.messages, message],
        });
      });
    },
    [update]
  );

  /** Update the currentStep text without changing status */
  const agentStep = useCallback(
    (agentId: string, currentStep: string) => {
      update((s) => updateAgent(s, agentId, { currentStep }));
    },
    [update]
  );

  /** Mark an agent as completed */
  const agentComplete = useCallback(
    (agentId: string, finalStep?: string) => {
      update((s) =>
        updateAgent(s, agentId, {
          status: 'completed',
          currentStep: finalStep || s.agents.find((a) => a.id === agentId)?.currentStep || '',
          endTime: Date.now(),
        })
      );
    },
    [update]
  );

  /** Mark an agent as errored */
  const agentError = useCallback(
    (agentId: string, errorMsg: string) => {
      update((s) =>
        updateAgent(s, agentId, {
          status: 'error',
          error: errorMsg,
          endTime: Date.now(),
        })
      );
    },
    [update]
  );

  /** Mark an agent as waiting */
  const agentWaiting = useCallback(
    (agentId: string, waitingFor?: string) => {
      update((s) =>
        updateAgent(s, agentId, {
          status: 'waiting',
          currentStep: waitingFor || 'Waiting...',
        })
      );
    },
    [update]
  );

  /** Transition the overall workflow phase */
  const setPhase = useCallback(
    (phase: WorkflowPhase) => {
      update((s) => ({
        ...s,
        phase,
        overallProgress:
          phase === 'error'
            ? s.overallProgress
            : PHASE_PROGRESS[phase],
      }));
    },
    [update]
  );

  /** Set a custom progress value (for mid-execution granularity) */
  const setProgress = useCallback(
    (progress: number) => {
      update((s) => ({ ...s, overallProgress: Math.min(100, progress) }));
    },
    [update]
  );

  /** Reset to idle */
  const reset = useCallback(() => {
    update(() => createInitialWorkflow());
  }, [update]);

  return {
    workflowState,
    wf: {
      startNewQuery,
      agentStart,
      agentLog,
      agentStep,
      agentComplete,
      agentError,
      agentWaiting,
      setPhase,
      setProgress,
      reset,
    },
  };
}
