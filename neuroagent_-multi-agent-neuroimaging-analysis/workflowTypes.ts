export type WorkflowPhase =
  | 'idle'
  | 'classifying'
  | 'planning'
  | 'validating'
  | 'executing'
  | 'researching'
  | 'done'
  | 'error';

/** One record per user query */
export interface WorkflowRecord {
  id: string;
  query: string;
  phase: WorkflowPhase;
  overallProgress: number;
  /** Index in the global messages array where this query's messages start */
  startIndex: number;
  /** Index where they end (-1 means still in progress / extends to current end) */
  endIndex: number;
  /** Elapsed seconds when completed */
  elapsedSeconds: number;
}

export interface WorkflowHistory {
  records: WorkflowRecord[];
  /** ID of the currently active workflow (null if idle) */
  activeId: string | null;
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

export function createInitialHistory(): WorkflowHistory {
  return {
    records: [],
    activeId: null,
  };
}

let _idCounter = 0;
export function generateWorkflowId(): string {
  _idCounter++;
  return `wf-${Date.now()}-${_idCounter}`;
}
