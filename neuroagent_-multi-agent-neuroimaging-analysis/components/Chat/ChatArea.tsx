import React, { useEffect, useRef, useState, useMemo } from 'react';
import { ChatMessage, AgentType } from '../../types';
import { WorkflowHistory, WorkflowRecord } from '../../workflowTypes';
import MessageBubble from './MessageBubble';
import ThinkingOverlay from '../AgentProgress/ThinkingOverlay';
import { Send, Upload, PlayCircle } from 'lucide-react';

const OUTER_CHAT_ROLES = new Set([
  AgentType.USER,
  AgentType.EXECUTOR,
  AgentType.RESEARCHER,
  AgentType.SYSTEM,
]);

interface ChatAreaProps {
  messages: ChatMessage[];
  onSendMessage: (text: string) => void;
  onFileUpload: (file: File) => void;
  onLoadDemo: () => void;
  isProcessing: boolean;
  hasData: boolean;
  highlightedMessageId: string | null;
  onRestartStep: (messageId: string, newParams: any) => void;
  history: WorkflowHistory;
}

/**
 * Build the render sequence: outer messages interleaved with ThinkingOverlay bars.
 * For each workflow record, we insert its collapsed bar at the position
 * where its first outer-visible message would appear (or at its startIndex).
 */
interface RenderItem {
  type: 'message' | 'thinking';
  message?: ChatMessage;
  record?: WorkflowRecord;
  workflowMessages?: ChatMessage[];
}

function buildRenderItems(
  messages: ChatMessage[],
  records: WorkflowRecord[]
): RenderItem[] {
  const items: RenderItem[] = [];
  const recordsByStart = [...records].sort((a, b) => a.startIndex - b.startIndex);

  let nextRecordIdx = 0;

  for (let i = 0; i < messages.length; i++) {
    // Insert any workflow bars that start at or before this message index
    while (nextRecordIdx < recordsByStart.length && recordsByStart[nextRecordIdx].startIndex <= i) {
      const rec = recordsByStart[nextRecordIdx];
      const end = rec.endIndex === -1 ? messages.length : rec.endIndex;
      const wfMessages = messages.slice(rec.startIndex, end);
      items.push({ type: 'thinking', record: rec, workflowMessages: wfMessages });
      nextRecordIdx++;
    }

    const msg = messages[i];
    if (OUTER_CHAT_ROLES.has(msg.role)) {
      items.push({ type: 'message', message: msg });
    }
  }

  // Any remaining workflows (e.g., active one at the end)
  while (nextRecordIdx < recordsByStart.length) {
    const rec = recordsByStart[nextRecordIdx];
    const end = rec.endIndex === -1 ? messages.length : rec.endIndex;
    const wfMessages = messages.slice(rec.startIndex, end);
    items.push({ type: 'thinking', record: rec, workflowMessages: wfMessages });
    nextRecordIdx++;
  }

  return items;
}

const ChatArea: React.FC<ChatAreaProps> = ({
  messages, onSendMessage, onFileUpload, onLoadDemo, isProcessing,
  hasData, highlightedMessageId, onRestartStep, history,
}) => {
  const [input, setInput] = useState('');
  const [expandedWorkflowId, setExpandedWorkflowId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const messageRefs = useRef<{ [key: string]: HTMLDivElement | null }>({});

  // Live elapsed timer for the active workflow
  const [liveElapsed, setLiveElapsed] = useState(0);
  const liveTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const liveStartRef = useRef<number | null>(null);

  useEffect(() => {
    if (history.activeId) {
      if (!liveStartRef.current) liveStartRef.current = Date.now();
      liveTimerRef.current = setInterval(() => {
        if (liveStartRef.current) setLiveElapsed(Math.floor((Date.now() - liveStartRef.current) / 1000));
      }, 1000);
    } else {
      if (liveTimerRef.current) { clearInterval(liveTimerRef.current); liveTimerRef.current = null; }
      liveStartRef.current = null;
    }
    return () => { if (liveTimerRef.current) clearInterval(liveTimerRef.current); };
  }, [history.activeId]);

  // Reset timer when a new query starts
  useEffect(() => {
    if (history.activeId) {
      liveStartRef.current = Date.now();
      setLiveElapsed(0);
    }
  }, [history.activeId]);

  // Build render items
  const renderItems = useMemo(
    () => buildRenderItems(messages, history.records),
    [messages, history.records]
  );

  // Auto-scroll
  const scrollToBottom = () => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });

  useEffect(() => {
    if (!highlightedMessageId && !expandedWorkflowId) scrollToBottom();
  }, [messages.length, highlightedMessageId, expandedWorkflowId]);

  useEffect(() => {
    if (highlightedMessageId && !expandedWorkflowId && messageRefs.current[highlightedMessageId]) {
      messageRefs.current[highlightedMessageId]?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [highlightedMessageId, expandedWorkflowId]);

  // When highlightedMessageId changes, check if it belongs to a workflow's thinking messages
  // If so, auto-expand that workflow
  useEffect(() => {
    if (!highlightedMessageId) return;
    const msgIdx = messages.findIndex((m) => m.id === highlightedMessageId);
    if (msgIdx === -1) return;
    const msg = messages[msgIdx];

    // If the message is NOT an outer-chat role, it's a thinking message
    if (!OUTER_CHAT_ROLES.has(msg.role)) {
      // Find which workflow it belongs to
      for (const rec of history.records) {
        const end = rec.endIndex === -1 ? messages.length : rec.endIndex;
        if (msgIdx >= rec.startIndex && msgIdx < end) {
          setExpandedWorkflowId(rec.id);
          break;
        }
      }
    }
  }, [highlightedMessageId, history.records, messages]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (input.trim() && !isProcessing) {
      onSendMessage(input);
      setInput('');
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) onFileUpload(e.target.files[0]);
  };

  // Deduplicate: track which workflow IDs we've already rendered
  const renderedWorkflows = new Set<string>();

  return (
    <div className="flex flex-col h-full bg-slate-900 border-l border-slate-800 relative">
      <div className="flex-none p-4 border-b border-slate-800 bg-slate-900/50 backdrop-blur">
        <h2 className="text-lg font-semibold text-slate-100 flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
          Research Assistant
        </h2>
        <p className="text-xs text-slate-400">Multi-Agent System Active</p>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-2 custom-scrollbar">
        {renderItems.map((item, idx) => {
          if (item.type === 'message' && item.message) {
            return (
              <div key={item.message.id} ref={(el) => { messageRefs.current[item.message!.id] = el; }}>
                <MessageBubble
                  message={item.message}
                  isHighlighted={item.message.id === highlightedMessageId}
                  // No onRestart in outer chat
                />
              </div>
            );
          }

          if (item.type === 'thinking' && item.record) {
            // Skip if already rendered (dedup)
            if (renderedWorkflows.has(item.record.id)) return null;
            renderedWorkflows.add(item.record.id);

            const rec = item.record;
            const isActiveWf = rec.id === history.activeId;
            // Re-compute live messages for active workflow
            const wfMsgs = isActiveWf
              ? messages.slice(rec.startIndex)
              : item.workflowMessages!;

            return (
              <ThinkingOverlay
                key={rec.id}
                record={rec}
                isActive={isActiveWf}
                workflowMessages={wfMsgs}
                highlightedMessageId={highlightedMessageId}
                onRestartStep={onRestartStep}
                isExpanded={expandedWorkflowId === rec.id}
                onRequestExpand={() => setExpandedWorkflowId(rec.id)}
                onRequestCollapse={() => setExpandedWorkflowId(null)}
                elapsedSeconds={isActiveWf ? liveElapsed : rec.elapsedSeconds}
              />
            );
          }

          return null;
        })}

        <div ref={messagesEndRef} />
      </div>

      <div className="flex-none p-4 bg-slate-900 border-t border-slate-800">
        {!hasData ? (
          <div className="mb-4 p-4 bg-slate-800/50 rounded-lg border border-dashed border-slate-700 text-center">
            <p className="text-sm text-slate-300 mb-3">Upload a CSV dataset to begin analysis</p>
            <div className="flex justify-center gap-3">
              <button onClick={() => fileInputRef.current?.click()} className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded text-sm transition-colors">
                <Upload className="w-4 h-4" /> Upload CSV
              </button>
              <button onClick={onLoadDemo} className="flex items-center gap-2 px-4 py-2 bg-slate-700 hover:bg-slate-600 text-slate-200 rounded text-sm transition-colors">
                <PlayCircle className="w-4 h-4" /> Load Demo Data
              </button>
            </div>
          </div>
        ) : null}

        <form onSubmit={handleSubmit} className="relative">
          <input
            type="text" value={input} onChange={(e) => setInput(e.target.value)}
            disabled={isProcessing}
            placeholder={hasData ? "Ask about the data (e.g., 'Correlation between Amyloid and Age?')" : 'Upload data first...'}
            className="w-full bg-slate-800 text-slate-200 rounded-lg pl-4 pr-12 py-3 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 border border-slate-700 disabled:opacity-50 placeholder-slate-500"
          />
          <button type="submit" disabled={!input.trim() || isProcessing}
            className="absolute right-2 top-2 p-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-md disabled:opacity-50 disabled:hover:bg-indigo-600 transition-colors">
            <Send className="w-4 h-4" />
          </button>
        </form>
        <input type="file" ref={fileInputRef} onChange={handleFileChange} accept=".csv" className="hidden" />
      </div>
    </div>
  );
};

export default ChatArea;
