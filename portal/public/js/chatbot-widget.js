/**
 * EnMS Chatbot Widget
 * Embeddable floating chatbot for EnMS Portal
 * Connects to Rasa backend via /api/chatbot/api/rasa/webhook
 */

(function() {
    'use strict';

    // Configuration
    const CONFIG = {
        backendUrl: '/api/chatbot',  // Proxied through nginx
        welcomeMessage: 'Hello! I can help with ISO 50001, HumanEnerDIA how-to guidance, reports, and troubleshooting.',
        placeholder: 'Type your message...',
        title: 'HumanEnerDIA Assistant',
        sessionPrefix: 'enms_chat_'
    };

    // Session management
    let sessionId = CONFIG.sessionPrefix + Date.now() + '_' + Math.random().toString(36).substring(2, 15);
    let isOpen = false;
    let isLoading = false;

    // Create widget HTML
    function createWidget() {
        const widgetHTML = `
            <div id="enms-chatbot-widget" class="enms-chat-closed">
                <!-- Toggle Button -->
                <button id="enms-chat-toggle" class="enms-chat-toggle" aria-label="Open chat">
                    <svg class="enms-chat-icon-open" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
                    </svg>
                    <svg class="enms-chat-icon-close" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="display:none">
                        <path d="M18 6L6 18M6 6l12 12"></path>
                    </svg>
                </button>

                <!-- Chat Window -->
                <div id="enms-chat-window" class="enms-chat-window">
                    <!-- Header -->
                    <div class="enms-chat-header">
                        <div class="enms-chat-header-info">
                            <div class="enms-chat-avatar">
                                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <circle cx="12" cy="12" r="10"></circle>
                                    <path d="M8 14s1.5 2 4 2 4-2 4-2"></path>
                                    <line x1="9" y1="9" x2="9.01" y2="9"></line>
                                    <line x1="15" y1="9" x2="15.01" y2="9"></line>
                                </svg>
                            </div>
                            <div>
                                <div class="enms-chat-title">${CONFIG.title}</div>
                                <div class="enms-chat-status">Online</div>
                            </div>
                        </div>
                        <button id="enms-chat-minimize" class="enms-chat-minimize" aria-label="Minimize">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M18 6L6 18M6 6l12 12"></path>
                            </svg>
                        </button>
                    </div>

                    <!-- Messages -->
                    <div id="enms-chat-messages" class="enms-chat-messages">
                        <div class="enms-chat-message enms-chat-bot">
                            <div class="enms-chat-bubble">${CONFIG.welcomeMessage}</div>
                        </div>
                        <!-- Quick Reply Buttons -->
                        <div id="enms-quick-replies" class="enms-quick-replies">
                            <div class="enms-quick-replies-title">💡 Quick suggestions:</div>
                            <button class="enms-quick-reply-btn" data-query="How do I get started with HumanEnerDIA?">How do I get started?</button>
                            <button class="enms-quick-reply-btn" data-query="What is ISO 50001?">What is ISO 50001?</button>
                            <button class="enms-quick-reply-btn" data-query="How many Grafana dashboards are there?">Grafana dashboards</button>
                            <button class="enms-quick-reply-btn" data-query="Why is my Grafana dashboard not showing data?">Troubleshooting</button>
                            <button class="enms-quick-reply-btn" data-query="What is an energy baseline?">Energy baseline</button>
                        </div>
                    </div>

                    <!-- Input -->
                    <div class="enms-chat-input-container">
                        <input 
                            type="text" 
                            id="enms-chat-input" 
                            class="enms-chat-input" 
                            placeholder="${CONFIG.placeholder}"
                            autocomplete="off"
                        >
                        <button id="enms-chat-send" class="enms-chat-send" aria-label="Send">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <line x1="22" y1="2" x2="11" y2="13"></line>
                                <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
                            </svg>
                        </button>
                    </div>
                </div>
            </div>
        `;

        // Create container and add to body
        const container = document.createElement('div');
        container.innerHTML = widgetHTML;
        document.body.appendChild(container.firstElementChild);
    }

    // Create widget styles
    function createStyles() {
        const styles = `
            #enms-chatbot-widget {
                position: fixed;
                bottom: 20px;
                right: 20px;
                z-index: 10000;
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            }

            .enms-chat-toggle {
                width: 56px;
                height: 56px;
                border-radius: 50%;
                background: linear-gradient(135deg, #0A2463 0%, #1E3A8A 100%);
                border: none;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                box-shadow: 0 4px 20px rgba(10, 36, 99, 0.4);
                transition: all 0.3s ease;
                color: white;
            }

            .enms-chat-toggle:hover {
                transform: scale(1.1);
                box-shadow: 0 6px 28px rgba(10, 36, 99, 0.5);
            }

            .enms-chat-window {
                position: absolute;
                bottom: 70px;
                right: 0;
                width: 380px;
                height: 520px;
                background: white;
                border-radius: 16px;
                box-shadow: 0 10px 40px rgba(0, 0, 0, 0.15);
                display: none;
                flex-direction: column;
                overflow: hidden;
                animation: enms-chat-slide-up 0.3s ease;
            }

            @keyframes enms-chat-slide-up {
                from {
                    opacity: 0;
                    transform: translateY(20px);
                }
                to {
                    opacity: 1;
                    transform: translateY(0);
                }
            }

            .enms-chat-closed .enms-chat-window {
                display: none;
            }

            .enms-chat-open .enms-chat-window {
                display: flex;
            }

            .enms-chat-open .enms-chat-icon-open {
                display: none;
            }

            .enms-chat-open .enms-chat-icon-close {
                display: block !important;
            }

            .enms-chat-header {
                background: linear-gradient(135deg, #0A2463 0%, #1E3A8A 100%);
                color: white;
                padding: 16px 20px;
                display: flex;
                align-items: center;
                justify-content: space-between;
            }

            .enms-chat-header-info {
                display: flex;
                align-items: center;
                gap: 12px;
            }

            .enms-chat-avatar {
                width: 40px;
                height: 40px;
                background: rgba(255, 255, 255, 0.2);
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
            }

            .enms-chat-title {
                font-weight: 600;
                font-size: 16px;
            }

            .enms-chat-status {
                font-size: 12px;
                opacity: 0.8;
            }

            .enms-chat-minimize {
                background: rgba(255, 255, 255, 0.1);
                border: none;
                border-radius: 8px;
                padding: 8px;
                cursor: pointer;
                color: white;
                transition: background 0.2s;
            }

            .enms-chat-minimize:hover {
                background: rgba(255, 255, 255, 0.2);
            }

            .enms-chat-messages {
                flex: 1;
                overflow-y: auto;
                padding: 20px;
                display: flex;
                flex-direction: column;
                gap: 12px;
                background: #f8f9fa;
            }

            .enms-chat-message {
                display: flex;
                flex-direction: column;
                max-width: 85%;
            }

            .enms-chat-user {
                align-self: flex-end;
            }

            .enms-chat-bot {
                align-self: flex-start;
            }

            .enms-chat-bubble {
                padding: 12px 16px;
                border-radius: 16px;
                font-size: 14px;
                line-height: 1.5;
                word-wrap: break-word;
            }

            .enms-chat-user .enms-chat-bubble {
                background: linear-gradient(135deg, #0A2463 0%, #1E3A8A 100%);
                color: white;
                border-bottom-right-radius: 4px;
            }

            .enms-chat-bot .enms-chat-bubble {
                background: white;
                color: #1f2937;
                border-bottom-left-radius: 4px;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
            }

            .enms-chat-input-container {
                padding: 16px;
                background: white;
                border-top: 1px solid #e5e7eb;
                display: flex;
                gap: 12px;
            }

            .enms-chat-input {
                flex: 1;
                padding: 12px 16px;
                border: 1px solid #e5e7eb;
                border-radius: 24px;
                font-size: 14px;
                outline: none;
                transition: border-color 0.2s;
            }

            .enms-chat-input:focus {
                border-color: #0A2463;
            }

            .enms-chat-send {
                width: 44px;
                height: 44px;
                border-radius: 50%;
                background: linear-gradient(135deg, #0A2463 0%, #1E3A8A 100%);
                border: none;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                transition: all 0.2s;
            }

            .enms-chat-send:hover {
                transform: scale(1.05);
            }

            .enms-chat-send:disabled {
                opacity: 0.5;
                cursor: not-allowed;
                transform: none;
            }

            .enms-chat-typing {
                display: flex;
                align-items: center;
                gap: 4px;
                padding: 12px 16px;
                background: white;
                border-radius: 16px;
                border-bottom-left-radius: 4px;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
            }

            .enms-chat-typing-dot {
                width: 8px;
                height: 8px;
                background: #6b7280;
                border-radius: 50%;
                animation: enms-typing 1.4s infinite ease-in-out;
            }

            .enms-chat-typing-dot:nth-child(1) { animation-delay: 0s; }
            .enms-chat-typing-dot:nth-child(2) { animation-delay: 0.2s; }
            .enms-chat-typing-dot:nth-child(3) { animation-delay: 0.4s; }

            @keyframes enms-typing {
                0%, 60%, 100% { transform: translateY(0); }
                30% { transform: translateY(-6px); }
            }

            .enms-chat-error {
                background: #fef2f2 !important;
                color: #dc2626 !important;
            }

            /* Mobile responsive */
            @media (max-width: 480px) {
                .enms-chat-window {
                    width: calc(100vw - 40px);
                    height: calc(100vh - 120px);
                    bottom: 80px;
                    right: -10px;
                }
            }

            /* Quick Reply Buttons */
            .enms-quick-replies {
                padding: 16px;
                display: flex;
                flex-direction: column;
                gap: 8px;
                border-top: 1px solid #e5e7eb;
                background: #f9fafb;
            }

            .enms-quick-replies-title {
                font-size: 13px;
                font-weight: 600;
                color: #6b7280;
                margin-bottom: 4px;
            }

            .enms-quick-reply-btn {
                padding: 10px 14px;
                background: white;
                border: 1px solid #d1d5db;
                border-radius: 8px;
                color: #374151;
                font-size: 14px;
                cursor: pointer;
                text-align: left;
                transition: all 0.2s;
            }

            .enms-quick-reply-btn:hover {
                background: #3b82f6;
                color: white;
                border-color: #3b82f6;
                transform: translateX(2px);
            }
        `;

        const styleSheet = document.createElement('style');
        styleSheet.textContent = styles;
        document.head.appendChild(styleSheet);
    }

    // Toggle chat window
    function toggleChat() {
        const widget = document.getElementById('enms-chatbot-widget');
        isOpen = !isOpen;
        widget.className = isOpen ? 'enms-chat-open' : 'enms-chat-closed';
        
        if (isOpen) {
            document.getElementById('enms-chat-input').focus();
        }
    }

    // Add message to chat
    function addMessage(text, isUser = false, isError = false) {
        const messagesContainer = document.getElementById('enms-chat-messages');
        const messageDiv = document.createElement('div');
        messageDiv.className = `enms-chat-message ${isUser ? 'enms-chat-user' : 'enms-chat-bot'}`;
        
        const bubble = document.createElement('div');
        bubble.className = `enms-chat-bubble ${isError ? 'enms-chat-error' : ''}`;
        bubble.textContent = text;
        
        messageDiv.appendChild(bubble);
        messagesContainer.appendChild(messageDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
        
        return bubble;
    }

    // Show typing indicator
    function showTyping() {
        const messagesContainer = document.getElementById('enms-chat-messages');
        const typingDiv = document.createElement('div');
        typingDiv.id = 'enms-typing-indicator';
        typingDiv.className = 'enms-chat-message enms-chat-bot';
        typingDiv.innerHTML = `
            <div class="enms-chat-typing">
                <div class="enms-chat-typing-dot"></div>
                <div class="enms-chat-typing-dot"></div>
                <div class="enms-chat-typing-dot"></div>
            </div>
        `;
        messagesContainer.appendChild(typingDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    // Hide typing indicator
    function hideTyping() {
        const typing = document.getElementById('enms-typing-indicator');
        if (typing) typing.remove();
    }

    // Send message to backend
    async function sendMessage(text) {
        if (!text.trim() || isLoading) return;

        isLoading = true;
        const input = document.getElementById('enms-chat-input');
        const sendBtn = document.getElementById('enms-chat-send');
        
        input.disabled = true;
        sendBtn.disabled = true;

        // Add user message
        addMessage(text, true);
        input.value = '';

        // Show typing
        showTyping();

        try {
            const response = await fetch(`${CONFIG.backendUrl}/api/rasa/webhook`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    sender: sessionId,
                    message: text
                }),
            });

            hideTyping();

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const data = await response.json();

            if (Array.isArray(data) && data.length > 0) {
                for (const item of data) {
                    if (item.text) {
                        addMessage(item.text);
                    }
                }
            } else {
                // Rasa returned empty - provide helpful fallback
                addMessage("I can help with ISO 50001, HumanEnerDIA pages, reports, energy-management concepts, and troubleshooting. For live machine status or current energy values, use OVOS or the live dashboards.", false, false);
            }

        } catch (error) {
            hideTyping();
            console.error('Chatbot error:', error);
            addMessage('Connection error. The chatbot service may not be running.', false, true);
        }

        isLoading = false;
        input.disabled = false;
        sendBtn.disabled = false;
        input.focus();
    }

    // Initialize widget
    function init() {
        createStyles();
        createWidget();

        // Event listeners
        document.getElementById('enms-chat-toggle').addEventListener('click', toggleChat);
        document.getElementById('enms-chat-minimize').addEventListener('click', toggleChat);
        
        document.getElementById('enms-chat-send').addEventListener('click', () => {
            const input = document.getElementById('enms-chat-input');
            sendMessage(input.value);
        });

        document.getElementById('enms-chat-input').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                sendMessage(e.target.value);
            }
        });

        // Quick reply button listeners
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('enms-quick-reply-btn')) {
                const query = e.target.getAttribute('data-query');
                sendMessage(query);
                // Hide quick replies after first use
                const quickReplies = document.getElementById('enms-quick-replies');
                if (quickReplies) {
                    quickReplies.style.display = 'none';
                }
            }
        });

        console.log('✅ EnMS Chatbot Widget loaded');
    }

    // Wait for DOM
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
