import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Send, Image as ImageIcon, X, Trash2, Zap, MessageCircle, Minimize2 } from 'lucide-react';
import { Message, Role, Attachment } from './types';
import { initChat, sendMessageStream } from './services/ovos';
import { generateId, fileToAttachment } from './utils/helpers';
import MessageBubble from './components/MessageBubble';
import TypingIndicator from './components/TypingIndicator';

const ChatBotUI: React.FC = () => {
  // State for Chat Widget visibility
  const [isOpen, setIsOpen] = useState(false);
  const [showQuickReplies, setShowQuickReplies] = useState(true);

  const [messages, setMessages] = useState<Message[]>([]);
  const [inputText, setInputText] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [thinkingEnabled, setThinkingEnabled] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Quick reply suggestions for first-time users
  const QUICK_REPLIES = [
    "How do I get started with HumanEnerDIA?",
    "What is ISO 50001?",
    "How many Grafana dashboards are there?",
    "Why is my Grafana dashboard not showing data?",
    "What is an energy baseline?"
  ];

  // Initialize chat on mount
  useEffect(() => {
    initChat();
    setMessages([{
      id: generateId(),
      role: Role.MODEL,
      text: "Merhaba! Size nasıl yardımcı olabilirim?",
      timestamp: Date.now()
    }]);
  }, []);

  // Auto-scroll to bottom
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    if (isOpen) {
      setTimeout(scrollToBottom, 100); // Slight delay for animation
    }
  }, [messages, isLoading, isOpen]);

  // Handle textarea auto-resize
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 100)}px`;
    }
  }, [inputText]);

  const handleQuickReply = (text: string) => {
    setInputText(text);
    setShowQuickReplies(false);
    // Auto-submit after slight delay for better UX
    setTimeout(() => {
      handleSendMessage();
    }, 100);
  };

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      try {
        if (!file.type.startsWith('image/')) {
          throw new Error('Please select an image file.');
        }
        const attachment = await fileToAttachment(file);
        setAttachments(prev => [...prev, attachment]);
      } catch (err: any) {
        setError(err.message);
        setTimeout(() => setError(null), 3000);
      }
      e.target.value = '';
    }
  };

  const removeAttachment = (index: number) => {
    setAttachments(prev => prev.filter((_, i) => i !== index));
  };

  const handleResetChat = () => {
    if (window.confirm("Sohbeti temizlemek istediğinize emin misiniz?")) {
      initChat();
      setMessages([{
        id: generateId(),
        role: Role.MODEL,
        text: "Sohbet temizlendi.",
        timestamp: Date.now()
      }]);
      setAttachments([]);
      setInputText('');
    }
  };

  const handleSendMessage = useCallback(async () => {
    if ((!inputText.trim() && attachments.length === 0) || isLoading) return;

    const userMessageText = inputText.trim();
    const currentAttachments = [...attachments];

    setInputText('');
    setAttachments([]);
    setShowQuickReplies(false); // Hide quick replies after first message
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
    setError(null);

    const newUserMsg: Message = {
      id: generateId(),
      role: Role.USER,
      text: userMessageText,
      attachments: currentAttachments.length > 0 ? currentAttachments : undefined,
      timestamp: Date.now()
    };

    setMessages(prev => [...prev, newUserMsg]);
    setIsLoading(true);

    try {
      const botMsgId = generateId();
      setMessages(prev => [...prev, {
        id: botMsgId,
        role: Role.MODEL,
        text: '',
        isStreaming: true,
        timestamp: Date.now()
      }]);

      await sendMessageStream(userMessageText, currentAttachments, thinkingEnabled, (chunkText) => {
        setMessages(prev => prev.map(msg =>
          msg.id === botMsgId
            ? { ...msg, text: msg.text + chunkText }
            : msg
        ));
      });

      setMessages(prev => prev.map(msg =>
        msg.id === botMsgId
          ? { ...msg, isStreaming: false }
          : msg
      ));

    } catch (err: any) {
      setError("Bir hata oluştu.");
      setMessages(prev => prev.filter(msg => !(msg.role === Role.MODEL && msg.isStreaming && msg.text === '')));
    } finally {
      setIsLoading(false);
    }
  }, [inputText, attachments, isLoading]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  return (
    <>
      {/* Floating Chat Widget Container */}
      <div
        className={`
          tw-fixed tw-bottom-20 tw-right-4 tw-z-50
          tw-w-[90vw] md:tw-w-[380px] tw-h-[600px] tw-max-h-[75vh]
          tw-bg-white tw-rounded-2xl tw-shadow-2xl tw-border tw-border-slate-200
          tw-flex tw-flex-col tw-overflow-hidden
          tw-transition-all tw-duration-300 tw-ease-in-out tw-origin-bottom-right
          ${isOpen ? 'tw-scale-100 tw-opacity-100 tw-translate-y-0' : 'tw-scale-95 tw-opacity-0 tw-translate-y-10 tw-pointer-events-none'}
        `}
      >
        {/* Header */}
        <header className="tw-flex-none tw-bg-gradient-to-r tw-from-blue-600 tw-to-indigo-600 tw-px-5 tw-py-4 tw-flex tw-items-center tw-justify-between tw-shadow-md tw-text-white">
          <div className="tw-flex tw-items-center tw-gap-3">
            <div className="tw-p-1.5 tw-bg-white/20 tw-rounded-lg tw-backdrop-blur-sm">
              <Zap size={18} className="tw-text-white" fill="currentColor" />
            </div>
            <div>
              <h2 className="tw-font-bold tw-text-sm tw-leading-tight">HumanEnerDIA Assistant</h2>
              <p className="tw-text-[10px] tw-text-blue-100 tw-font-medium tw-opacity-90">
                Online • AI Chatbot
              </p>
            </div>
          </div>
          <div className="tw-flex tw-gap-2">
            <button
              onClick={handleResetChat}
              className="tw-p-1.5 tw-text-blue-100 hover:tw-text-white hover:tw-bg-white/10 tw-rounded-full tw-transition-all"
              title="Temizle"
            >
              <Trash2 size={16} />
            </button>
            <button
              onClick={() => setIsOpen(false)}
              className="tw-p-1.5 tw-text-blue-100 hover:tw-text-white hover:tw-bg-white/10 tw-rounded-full tw-transition-all"
              title="Kapat"
            >
              <Minimize2 size={16} />
            </button>
          </div>
        </header>

        {/* Messages Area */}
        <main className="tw-flex-1 tw-overflow-y-auto tw-p-4 tw-bg-slate-50 tw-scroll-smooth">
          <div className="tw-flex tw-flex-col tw-min-h-full">
            {messages.map((msg) => (
              <MessageBubble key={msg.id} message={msg} />
            ))}

            {/* Quick Reply Buttons - Show only at start */}
            {showQuickReplies && messages.length === 1 && !isLoading && (
              <div className="tw-flex tw-flex-col tw-gap-2 tw-mt-4 tw-mb-2">
                <div className="tw-text-xs tw-text-slate-500 tw-font-medium tw-mb-1 tw-px-1">
                  💡 Quick suggestions:
                </div>
                {QUICK_REPLIES.map((query, idx) => {
                  // Extract short display text from full query
                  const displayText = query
                    .replace("How do I get started with HumanEnerDIA?", "How do I get started?")
                    .replace("How many Grafana dashboards are there?", "Grafana dashboards")
                    .replace("Why is my Grafana dashboard not showing data?", "Troubleshooting")
                    .replace("What is an energy baseline?", "Energy baseline");
                  
                  return (
                    <button
                      key={idx}
                      onClick={() => handleQuickReply(query)}
                      className="tw-text-left tw-px-4 tw-py-2.5 tw-bg-white tw-border tw-border-blue-200 tw-rounded-lg tw-text-sm tw-text-slate-700 hover:tw-bg-blue-50 hover:tw-border-blue-400 tw-transition-all tw-shadow-sm hover:tw-shadow-md tw-font-medium"
                    >
                      {displayText}
                    </button>
                  );
                })}
              </div>
            )}

            {isLoading && messages.length > 0 && !messages[messages.length - 1].isStreaming && (
              <div className="tw-flex tw-justify-start tw-mb-6">
                <TypingIndicator />
              </div>
            )}

            {error && (
              <div className="tw-mx-auto tw-my-4 tw-px-3 tw-py-1.5 tw-bg-red-100 tw-text-red-600 tw-rounded-lg tw-text-xs tw-font-medium tw-border tw-border-red-200 tw-animate-bounce tw-text-center">
                {error}
              </div>
            )}

            <div ref={messagesEndRef} className="tw-h-2" />
          </div>
        </main>

        {/* Input Area */}
        <footer className="tw-flex-none tw-p-3 tw-bg-white tw-border-t tw-border-slate-100">

          {/* Attachment Previews */}
          {attachments.length > 0 && (
            <div className="tw-flex tw-gap-2 tw-mb-2 tw-overflow-x-auto tw-py-1 tw-px-1">
              {attachments.map((att, idx) => (
                <div key={idx} className="tw-relative tw-group tw-flex-shrink-0">
                  <img
                    src={`data:${att.mimeType};base64,${att.data}`}
                    alt="preview"
                    className="tw-w-12 tw-h-12 tw-object-cover tw-rounded-md tw-border tw-border-slate-200"
                  />
                  <button
                    onClick={() => removeAttachment(idx)}
                    className="tw-absolute -tw-top-1.5 -tw-right-1.5 tw-bg-slate-800 tw-text-white tw-rounded-full tw-p-0.5 tw-opacity-90 hover:tw-scale-110 tw-transition-transform tw-shadow-sm"
                  >
                    <X size={10} />
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* Thinking Mode Toggle */}
          <div className="tw-flex tw-items-center tw-justify-between tw-px-4 tw-py-2 tw-border-t tw-border-slate-200">
            <div className="tw-flex tw-items-center tw-gap-2">
              <Zap size={16} className={thinkingEnabled ? "tw-text-yellow-500" : "tw-text-slate-400"} />
              <span className="tw-text-sm tw-text-slate-700">Thinking Mode</span>
              <span className="tw-text-xs tw-text-slate-500">
                {thinkingEnabled ? "(Slower, deeper reasoning)" : "(Fast responses)"}
              </span>
            </div>
            <button
              onClick={() => setThinkingEnabled(!thinkingEnabled)}
              className={`tw-relative tw-w-11 tw-h-6 tw-rounded-full tw-transition-colors ${
                thinkingEnabled ? "tw-bg-yellow-500" : "tw-bg-slate-300"
              }`}
              aria-label="Toggle thinking mode"
            >
              <div className={`tw-absolute tw-top-1 tw-left-1 tw-w-4 tw-h-4 tw-bg-white tw-rounded-full tw-transition-transform ${
                thinkingEnabled ? "tw-translate-x-5" : ""
              }`} />
            </button>
          </div>

          {/* Input Bar */}
          <div className="tw-flex tw-items-end tw-gap-2">
            <button
              onClick={() => fileInputRef.current?.click()}
              className="tw-p-2 tw-text-slate-400 hover:tw-text-blue-600 hover:tw-bg-blue-50 tw-rounded-full tw-transition-colors tw-flex-shrink-0"
            >
              <ImageIcon size={20} />
            </button>
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileSelect}
              accept="image/*"
              className="tw-hidden"
            />

            <div className="tw-flex-1 tw-bg-slate-100 tw-border tw-border-slate-200 tw-rounded-2xl tw-px-3 tw-py-2 focus-within:tw-ring-2 focus-within:tw-ring-blue-500/20 focus-within:tw-border-blue-500 tw-transition-all">
              <textarea
                ref={textareaRef}
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Mesaj yazın..."
                className="tw-w-full tw-max-h-24 tw-bg-transparent tw-border-none focus:tw-ring-0 tw-p-0 tw-text-sm tw-text-slate-800 placeholder:tw-text-slate-400 tw-resize-none"
                rows={1}
              />
            </div>

            <button
              onClick={handleSendMessage}
              disabled={isLoading || (!inputText.trim() && attachments.length === 0)}
              className={`tw-p-2 tw-rounded-full tw-shadow-sm tw-transition-all tw-duration-200 tw-flex-shrink-0
                ${(inputText.trim() || attachments.length > 0) && !isLoading
                  ? 'tw-bg-blue-600 tw-text-white hover:tw-bg-blue-700 hover:tw-scale-105'
                  : 'tw-bg-slate-200 tw-text-slate-400 tw-cursor-not-allowed'
                }`}
            >
              <Send size={18} className={isLoading ? 'tw-hidden' : 'tw-block'} />
              {isLoading && (
                <div className="tw-w-4.5 tw-h-4.5 tw-border-2 tw-border-slate-400/30 tw-border-t-blue-600 tw-rounded-full tw-animate-spin"></div>
              )}
            </button>
          </div>
          <div className="tw-text-center tw-mt-2">
            <span className="tw-text-[10px] tw-text-slate-400">Rasa AI tarafından desteklenmektedir.</span>
          </div>
        </footer>
      </div>

      {/* Floating Toggle Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={`
          tw-fixed tw-bottom-4 tw-right-4 tw-z-50
          tw-w-14 tw-h-14 tw-rounded-full tw-shadow-lg
          tw-flex tw-items-center tw-justify-center
          tw-transition-all tw-duration-300 hover:tw-scale-110
          ${isOpen ? 'tw-bg-slate-800 tw-rotate-90' : 'tw-bg-blue-600 hover:tw-bg-blue-700 tw-rotate-0'}
        `}
      >
        {isOpen ? (
          <X size={24} className="tw-text-white" />
        ) : (
          <MessageCircle size={28} className="tw-text-white" />
        )}

        {/* Notification dot (optional visual flair) */}
        {!isOpen && messages.length > 1 && (
          <span className="tw-absolute tw-top-0 tw-right-0 tw-flex tw-h-4 tw-w-4">
            <span className="tw-animate-ping tw-absolute tw-inline-flex tw-h-full tw-w-full tw-rounded-full tw-bg-red-400 tw-opacity-75"></span>
            <span className="tw-relative tw-inline-flex tw-rounded-full tw-h-4 tw-w-4 tw-bg-red-500 tw-border-2 tw-border-white"></span>
          </span>
        )}
      </button>
    </>
  );
};

export default ChatBotUI;