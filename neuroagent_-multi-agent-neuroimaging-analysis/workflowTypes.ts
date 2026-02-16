export type WorkflowPhase =
  | 'idle'
  | 'classifying'
  | 'planning'
  | 'validating'
  | 'executing'
  | 'researching'
  | 'done'
  | 'error';

export interface WorkflowState {
  query: string;
  phase: WorkflowPhase;
  overallProgress: number;
  executionStepsDone: number;
  executionStepsTotal: number;
  /** Index into the messages array where this query's messages start */
  queryStartIndex: number;
}

export const PHASE_BASE_PROGRESS: Record<string, number> = {
  idle: 0,
  classifying: 0,
  planning: 20,
  validating: 40,
  executing: 60,
  researching: 80,
  done: 100,
  error: -1,
};

export function createInitialWorkflow(): WorkflowState {
  return {
    query: '',
    phase: 'idle',
    overallProgress: 0,
    executionStepsDone: 0,
    executionStepsTotal: 0,
    queryStartIndex: 0,
  };
}
