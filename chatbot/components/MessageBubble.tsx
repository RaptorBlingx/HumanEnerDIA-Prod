import React from 'react';
import { Message, Role } from '../types';
import { formatTime } from '../utils/helpers';
import { User, Bot, Copy } from 'lucide-react';

interface MessageBubbleProps {
  message: Message;
}

const MessageBubble: React.FC<MessageBubbleProps> = ({ message }) => {
  const isUser = message.role === Role.USER;
  const linkClassName = isUser
    ? 'tw-underline tw-text-blue-100 hover:tw-text-white'
    : 'tw-underline tw-text-blue-600 hover:tw-text-blue-800';

  const renderInlineText = (text: string, keyPrefix: string) => {
    const parts: React.ReactNode[] = [];
    const inlinePattern = /(\*\*.*?\*\*|\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)|(https?:\/\/[^\s<]+))/g;
    let lastIndex = 0;
    let match: RegExpExecArray | null;
    let tokenIndex = 0;

    while ((match = inlinePattern.exec(text)) !== null) {
      if (match.index > lastIndex) {
        parts.push(text.slice(lastIndex, match.index));
      }

      if (match[2] && match[3]) {
        parts.push(
          <a
            key={`${keyPrefix}-link-${tokenIndex}`}
            href={match[3]}
            target="_blank"
            rel="noreferrer"
            className={linkClassName}
          >
            {match[2]}
          </a>
        );
      } else if (match[4]) {
        parts.push(
          <a
            key={`${keyPrefix}-url-${tokenIndex}`}
            href={match[4]}
            target="_blank"
            rel="noreferrer"
            className={linkClassName}
          >
            {match[4]}
          </a>
        );
      } else if (match[0].startsWith('**') && match[0].endsWith('**')) {
        parts.push(
          <strong key={`${keyPrefix}-bold-${tokenIndex}`}>
            {match[0].slice(2, -2)}
          </strong>
        );
      }

      lastIndex = inlinePattern.lastIndex;
      tokenIndex += 1;
    }

    if (lastIndex < text.length) {
      parts.push(text.slice(lastIndex));
    }

    return parts;
  };

  // Simple formatter to handle code blocks and bold text
  const renderText = (text: string) => {
    const parts = text.split(/(```[\s\S]*?```)/g);
    return parts.map((part, index) => {
      if (part.startsWith('```')) {
        const content = part.replace(/^```\w*\n?/, '').replace(/```$/, '');
        return (
          <div key={index} className="tw-my-2 tw-bg-gray-900 tw-text-gray-100 tw-p-3 tw-rounded-md tw-overflow-x-auto tw-text-sm tw-font-mono tw-relative tw-group">
             <button 
                onClick={() => navigator.clipboard.writeText(content)}
                className="tw-absolute tw-top-2 tw-right-2 tw-p-1 tw-bg-gray-700 tw-rounded tw-opacity-0 tw-group-hover:tw-opacity-100 tw-transition-opacity"
                title="Copy code"
             >
               <Copy size={12} className="tw-text-white" />
             </button>
            <pre className="tw-whitespace-pre-wrap tw-break-all">{content}</pre>
          </div>
        );
      }
      return (
        <span key={index} className="tw-whitespace-pre-wrap tw-leading-relaxed">
          {renderInlineText(part, `inline-${index}`)}
        </span>
      );
    });
  };

  return (
    <div className={`tw-flex tw-w-full ${isUser ? 'tw-justify-end' : 'tw-justify-start'} tw-mb-6 tw-group tw-animate-fade-in-up`}>
      <div className={`tw-flex tw-max-w-[85%] md:tw-max-w-[70%] ${isUser ? 'tw-flex-row-reverse' : 'tw-flex-row'} tw-items-start tw-gap-3`}>
        
        {/* Avatar */}
        <div className={`tw-flex-shrink-0 tw-w-8 tw-h-8 tw-rounded-full tw-flex tw-items-center tw-justify-center ${isUser ? 'tw-bg-primary tw-text-white' : 'tw-bg-green-600 tw-text-white'} tw-shadow-sm`}>
          {isUser ? <User size={16} /> : <Bot size={16} />}
        </div>

        {/* Bubble */}
        <div className={`tw-flex tw-flex-col ${isUser ? 'tw-items-end' : 'tw-items-start'}`}>
          <div className={`
            tw-relative tw-px-5 tw-py-3.5 tw-shadow-sm
            ${isUser 
              ? 'tw-bg-primary tw-text-white tw-rounded-2xl tw-rounded-tr-sm' 
              : 'tw-bg-white tw-border tw-border-gray-100 tw-text-gray-800 tw-rounded-2xl tw-rounded-tl-sm'
            }
          `}>
            {/* Attachments (Images) */}
            {message.attachments && message.attachments.length > 0 && (
              <div className="tw-flex tw-flex-wrap tw-gap-2 tw-mb-2">
                {message.attachments.map((att, idx) => (
                  <img 
                    key={idx}
                    src={`data:${att.mimeType};base64,${att.data}`} 
                    alt="attachment" 
                    className="tw-max-w-full tw-h-auto tw-max-h-64 tw-rounded-lg tw-border tw-border-gray-200"
                  />
                ))}
              </div>
            )}
            
            <div className="tw-text-sm md:tw-text-base tw-break-words">
              {renderText(message.text)}
            </div>
          </div>
          
          <span className={`tw-text-[10px] tw-text-gray-400 tw-mt-1 tw-px-1 ${isUser ? 'tw-text-right' : 'tw-text-left'}`}>
            {formatTime(message.timestamp)}
          </span>
        </div>

      </div>
    </div>
  );
};

export default MessageBubble;
