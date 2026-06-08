import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import ChatBotUI from './ChatBotUI';

const rootElement = document.getElementById('chatbot-ui');
if (!rootElement) {
  throw new Error("Could not find root element to mount to");
}

const root = ReactDOM.createRoot(rootElement);
root.render(
  <React.StrictMode>
    <div className="tw-relative tw-min-h-screen tw-bg-slate-50 tw-font-sans">
      <ChatBotUI />
    </div>
  </React.StrictMode>
);