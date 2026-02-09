import { LlmChatPanel } from './LlmChatPanel.jsx';

export const FloatingLLMChat = ({ isOpen, onToggle, messages, input, onInputChange, onSend }) => (
  <>
    <button
      onClick={onToggle}
      className={`fixed bottom-6 right-6 w-14 h-14 rounded-2xl shadow-panel flex items-center justify-center transition-all duration-200 z-50 ${
        isOpen ? 'bg-slate-600 hover:bg-slate-700 text-white' : 'bg-slate-850 text-white hover:shadow-glow'
      }`}
      title={isOpen ? 'Close Chat' : 'Open AI Assistant'}
    >
      {isOpen ? (
        <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
        </svg>
      ) : (
        <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
        </svg>
      )}
    </button>

    {isOpen && (
      <div className="fixed bottom-24 right-6 w-[380px] h-[520px] z-50 animate-slide-up">
        <LlmChatPanel
          messages={messages}
          input={input}
          onInputChange={onInputChange}
          onSend={onSend}
        />
      </div>
    )}
  </>
);
