// Workflow state types for AgentProgressPanel integration

export interface AgentStatus {
  id: string;
  name: string;
  model: string;
  icon: string;
  role: string;
  status: 'idle' | 'waiting' | 'running' | 'completed' | 'error';
  currentStep: string;
  messages: string[];
  startTime: number | null;
  endTime: number | null;
  error: string | null;
}

export type WorkflowPhase =
  | 'idle'
  | 'classifying'
  | 'planning'
  | 'validating'
  | 'preprocessing'
  | 'executing'
  | 'researching'
  | 'done'
  | 'error';

export interface WorkflowState {
  query: string;
  agents: AgentStatus[];
  phase: WorkflowPhase;
  overallProgress: number;
}

export const NEURO_AGENT_DEFINITIONS = [
  {
    id: 'orchestrator',
    name: 'Orchestrator',
    model: 'generalModel',
    icon: '🎯',
    role: 'Classify query intent (RESEARCH / GENERAL)',
  },
  {
    id: 'planner',
    name: 'Planner',
    model: 'varies',
    icon: '📋',
    role: 'Create structured analysis plan',
  },
  {
    id: 'validator',
    name: 'Validator',
    model: 'generalModel',
    icon: '✅',
    role: 'Verify plan correctness before execution',
  },
  {
    id: 'preprocessor',
    name: 'Preprocessor',
    model: 'neuroModel',
    icon: '🔧',
    role: 'Transform categorical data to numeric',
  },
  {
    id: 'executor',
    name: 'Executor',
    model: 'none',
    icon: '⚙️',
    role: 'Run analysis tools (Internal + MCP)',
  },
  {
    id: 'researcher',
    name: 'Researcher',
    model: 'neuroModel',
    icon: '🔬',
    role: 'Scientific interpretation of results',
  },
];

export function createInitialAgents(): AgentStatus[] {
  return NEURO_AGENT_DEFINITIONS.map((def) => ({
    ...def,
    status: 'idle' as const,
    currentStep: '',
    messages: [],
    startTime: null,
    endTime: null,
    error: null,
  }));
}

export function createInitialWorkflow(): WorkflowState {
  return {
    query: '',
    agents: createInitialAgents(),
    phase: 'idle',
    overallProgress: 0,
  };
}

// Progress mapping for each phase
export const PHASE_PROGRESS: Record<WorkflowPhase, number> = {
  idle: 0,
  classifying: 5,
  planning: 15,
  validating: 30,
  preprocessing: 45,
  executing: 60,
  researching: 80,
  done: 100,
  error: -1, // keep current progress on error
};
