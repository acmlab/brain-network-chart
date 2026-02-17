import React, { useState, useEffect } from 'react';
import { AgentType, ChatMessage } from '../../types';
import { AGENT_COLORS } from '../../constants';
import { User, BrainCircuit, Bot, Microscope, Terminal, GitFork, Lightbulb, Settings, FileCog, RotateCcw, Check, X, ShieldCheck } from 'lucide-react';

interface MessageBubbleProps {
  message: ChatMessage;
  isHighlighted?: boolean;
  onRestart?: (messageId: string, newParams: any) => void;
}

const getIcon = (role: AgentType) => {
  switch (role) {
    case AgentType.USER: return <User className="w-4 h-4" />;
    case AgentType.ORCHESTRATOR: return <GitFork className="w-4 h-4" />;
    case AgentType.NEURO_PLANNER: return <BrainCircuit className="w-4 h-4" />;
    case AgentType.GENERAL_PLANNER: return <Settings className="w-4 h-4" />;
    case AgentType.PLANNER: return <BrainCircuit className="w-4 h-4" />;
    case AgentType.PLAN_VALIDATOR: return <ShieldCheck className="w-4 h-4" />;
    case AgentType.PREPROCESSOR: return <FileCog className="w-4 h-4" />;
    case AgentType.EXECUTOR: return <Terminal className="w-4 h-4" />;
    case AgentType.RESEARCHER: return <Microscope className="w-4 h-4" />;
    case AgentType.SYSTEM: return <Bot className="w-4 h-4" />;
    default: return <Lightbulb className="w-4 h-4" />;
  }
};

const MessageBubble: React.FC<MessageBubbleProps> = ({ message, isHighlighted, onRestart }) => {
  const isUser = message.role === AgentType.USER;
  const colorClass = AGENT_COLORS[message.role] || AGENT_COLORS[AgentType.SYSTEM];
  
  const isPlanner = message.role === AgentType.NEURO_PLANNER || message.role === AgentType.GENERAL_PLANNER;
  const isExecutor = message.role === AgentType.EXECUTOR;

  const canEdit = onRestart && (
    (isExecutor && message.metadata?.params) || 
    (isPlanner && message.metadata?.plan)
  );

  const [isEditing, setIsEditing] = useState(false);
  const [editParams, setEditParams] = useState(() => {
    if (isExecutor && message.metadata?.params) {
        return JSON.stringify(message.metadata.params, null, 2);
    }
    if (isPlanner && message.metadata?.plan) {
        return JSON.stringify(message.metadata.plan, null, 2);
    }
    return '';
  });

  // Single glow flash on highlight
  const [isGlowing, setIsGlowing] = useState(false);
  useEffect(() => {
    if (isHighlighted) {
      setIsGlowing(true);
      const timer = setTimeout(() => setIsGlowing(false), 1200);
      return () => clearTimeout(timer);
    }
  }, [isHighlighted]);

  const handleRun = () => {
    try {
        const parsed = JSON.parse(editParams);
        if (onRestart) onRestart(message.id, parsed);
        setIsEditing(false);
    } catch (e) {
        alert("Invalid JSON format");
    }
  };

  return (
    <div className={`flex w-full mb-4 ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={`max-w-[85%] flex flex-col ${isUser ? 'items-end' : 'items-start'} transition-all duration-300 ${isHighlighted ? 'scale-105' : ''}`}>
        <div className={`flex items-center gap-2 mb-1 px-1 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
          <div className={`p-1 rounded-full ${isUser ? 'bg-slate-600' : 'bg-slate-700'} text-slate-200`}>
             {getIcon(message.role)}
          </div>
          <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">
            {message.role}
          </span>
          {message.metadata?.model && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-500 border border-slate-700 font-mono">
              {message.metadata.model}
            </span>
          )}
          <span className="text-[10px] text-slate-600">
            {new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </span>
        </div>
        
        <div className={`
            px-4 py-3 rounded-2xl text-sm leading-relaxed border shadow-sm whitespace-pre-wrap 
            ${colorClass} 
            ${isUser ? 'rounded-tr-none' : 'rounded-tl-none'}
            ${isHighlighted ? 'ring-2 ring-indigo-400' : ''}
            ${isGlowing ? 'animate-glow-flash' : ''}
        `}>
          {message.content}

          {canEdit && !isEditing && (
             <div className="mt-3 pt-2 border-t border-slate-700/50 flex justify-end">
                <button 
                  onClick={() => setIsEditing(true)}
                  className="flex items-center gap-1 text-xs text-indigo-300 hover:text-indigo-200 bg-slate-900/40 px-2 py-1 rounded"
                >
                    <RotateCcw className="w-3 h-3" /> {isPlanner ? 'Edit Plan & Restart' : 'Edit & Restart Step'}
                </button>
             </div>
          )}

          {isEditing && (
            <div className="mt-3 bg-slate-950/50 rounded p-2 border border-slate-700/50">
                <p className="text-xs text-slate-400 mb-1">
                    {isPlanner ? 'Edit Plan (JSON):' : 'Edit Tool Parameters (JSON):'}
                </p>
                <textarea 
                    value={editParams}
                    onChange={(e) => setEditParams(e.target.value)}
                    className="w-full h-48 bg-slate-900 text-xs font-mono text-slate-300 p-2 rounded border border-slate-700 focus:outline-none focus:border-indigo-500"
                />
                <div className="flex justify-end gap-2 mt-2">
                    <button 
                        onClick={() => setIsEditing(false)}
                        className="p-1 text-slate-400 hover:text-slate-200"
                    >
                        <X className="w-4 h-4" />
                    </button>
                    <button 
                        onClick={handleRun}
                        className="flex items-center gap-1 bg-indigo-600 hover:bg-indigo-500 text-white text-xs px-3 py-1 rounded"
                    >
                        <Check className="w-3 h-3" /> {isPlanner ? 'Update Plan' : 'Run'}
                    </button>
                </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default MessageBubble;