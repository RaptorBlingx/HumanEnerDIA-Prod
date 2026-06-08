import React from 'react';

const TypingIndicator: React.FC = () => {
  return (
    <div className="tw-flex tw-space-x-1.5 tw-p-2 tw-bg-gray-100 dark:tw-bg-gray-800 tw-rounded-2xl tw-w-fit tw-items-center tw-h-10">
      <div className="tw-w-2 tw-h-2 tw-bg-gray-400 tw-rounded-full tw-animate-bounce [animation-delay:-0.3s]"></div>
      <div className="tw-w-2 tw-h-2 tw-bg-gray-400 tw-rounded-full tw-animate-bounce [animation-delay:-0.15s]"></div>
      <div className="tw-w-2 tw-h-2 tw-bg-gray-400 tw-rounded-full tw-animate-bounce"></div>
    </div>
  );
};

export default TypingIndicator;
