/**
 * EnMS OVOS Voice Assistant Widget
 * Floating widget for OVOS voice assistant integration
 * Connects to OVOS via /api/v1/ovos/voice/query
 * 
 * SEPARATE from chatbot-widget.js (Rasa chatbot)
 * 
 * Created: December 1, 2025
 */

(function() {
    'use strict';

    // Keep the test-warning trigger visible during the current dev/demo phase.
    const devToolsEnabled = true;

    // Configuration
    const CONFIG = {
        // API endpoint - MUST use nginx proxy to avoid CORS issues
        // Browser on :8080 cannot directly access :8001 due to CORS
        apiUrl: window.location.port === '8001' 
            ? 'http://' + window.location.hostname + ':8001/api/v1/ovos/voice/query'  // Direct (when testing from :8001)
            : '/api/ovos/voice/query',     // Via nginx proxy (production - relative path)
        healthUrl: window.location.port === '8001' 
            ? 'http://' + window.location.hostname + ':8001/api/v1/ovos/voice/health'  // Direct (when testing from :8001)
            : '/api/ovos/voice/health',    // Via nginx proxy (production - relative path)
        activeAnomaliesUrl: window.location.port === '8001'
            ? 'http://' + window.location.hostname + ':8001/api/v1/anomaly/active'
            : '/api/analytics/api/v1/anomaly/active',
        machinesUrl: window.location.port === '8001'
            ? 'http://' + window.location.hostname + ':8001/api/v1/machines'
            : '/api/analytics/api/v1/machines',
        createAnomalyUrl: window.location.port === '8001'
            ? 'http://' + window.location.hostname + ':8001/api/v1/anomaly/create'
            : '/api/analytics/api/v1/anomaly/create',
        welcomeMessage: 'Hello! I\'m your EnMS voice assistant. Ask me about energy consumption, machine status, anomalies, forecasts, or say "factory overview" for a summary. Say "Jarvis" to activate hands-free!',
        placeholder: 'Ask about energy, machines, anomalies...',
        title: 'OVOS Voice Assistant',
        subtitle: 'Energy Management',
        devToolsEnabled: devToolsEnabled,
        sessionPrefix: 'enms_ovos_',
        // Porcupine Wake Word Config
        // Get free key at: https://console.picovoice.ai/
        porcupineAccessKey: 'm5P2rhLwLCydE9xgQLrIUovHrhOaiYXVrxcRHmdPBOMokPUVHbSTaQ==', // User must set this
        wakeWord: 'Jarvis'
    };

    // Session management
    let sessionId = CONFIG.sessionPrefix + Date.now() + '_' + Math.random().toString(36).substring(2, 15);
    let isOpen = false;
    let isLoading = false;
    let audioEnabled = true;  // TTS audio playback enabled by default
    let currentAudio = null;  // Track currently playing audio
    let abortController = null;  // Track current request for cancellation
    let activeMessageAnimation = null;
    let activeInsightsAnimation = null;

    const STREAMING_MIN_DELAY_MS = 22;
    const STREAMING_MAX_DELAY_MS = 70;
    const STREAMING_TARGET_TOTAL_MS = 2200;
    
    // Wake word state
    let wakeWordEnabled = false;
    let voicePermissionGranted = false;  // One-time permission flag
    let porcupine = null;
    let webVp = null;  // Web Voice Processor

    // WebSocket for proactive warnings (WASABI Phase 1)
    let ws = null;
    let reconnectAttempts = 0;
    const MAX_RECONNECT_DELAY = 30000; // 30 seconds
    const WS_URL = '/api/analytics/ws/anomalies'; // Relative path through nginx

    // Notification Management (WASABI Phase 1)
    let notifications = JSON.parse(localStorage.getItem('ovos_notifications') || '[]');
    let unreadCount = 0;
    let isTriggeringDevWarning = false;

    function normalizeNotifications(notificationList) {
        return notificationList
            .filter(notification => notification.severity !== 'normal')
            .sort((left, right) => new Date(right.timestamp) - new Date(left.timestamp));
    }

    // Load notifications from localStorage on startup
    function loadNotifications() {
        notifications = normalizeNotifications(
            JSON.parse(localStorage.getItem('ovos_notifications') || '[]')
        );
        unreadCount = notifications.filter(n => !n.read).length;
        saveNotifications();
        updateNotificationBadge();
        renderNotificationList();
    }

    // Save notifications to localStorage
    function saveNotifications() {
        localStorage.setItem('ovos_notifications', JSON.stringify(notifications));
    }

    // Add new notification
    function addNotification(data) {
        const backendId = data.backend_id || data.anomaly_id || data.id || null;
        const existingNotification = backendId
            ? notifications.find(n => n.backend_id === backendId)
            : null;

        if (existingNotification) {
            if (data.read === false && existingNotification.read) {
                existingNotification.read = false;
                unreadCount++;
                saveNotifications();
                updateNotificationBadge();
                renderNotificationList();
            }
            return existingNotification;
        }

        const notification = {
            id: Date.now() + Math.random().toString(36).substring(2, 9),
            backend_id: backendId,
            timestamp: data.timestamp || data.detected_at || new Date().toISOString(),
            message: data.message || 'New notification',
            severity: data.severity || 'warning',
            machine_id: data.machine_id || 'Unknown',
            metric: data.metric || '',
            value: data.value || '',
            expected: data.expected || '',
            read: data.read === true
        };
        
        // Add to beginning of array
        notifications.unshift(notification);
        
        // Keep only last 50 notifications
        if (notifications.length > 50) {
            notifications = notifications.slice(0, 50);
        }

        notifications = normalizeNotifications(notifications);
        
        if (!notification.read) {
            unreadCount++;
        }
        saveNotifications();
        updateNotificationBadge();
        renderNotificationList();
        
        return notification;
    }

    async function syncNotificationsFromBackend() {
        try {
            const response = await fetch(CONFIG.activeAnomaliesUrl, {
                credentials: 'same-origin'
            });

            if (!response.ok) {
                return;
            }

            const payload = await response.json();
            const anomalies = Array.isArray(payload.anomalies) ? payload.anomalies : [];

            anomalies
                .filter(anomaly => anomaly.severity !== 'normal')
                .slice()
                .reverse()
                .forEach(anomaly => {
                addNotification({
                    backend_id: anomaly.id ? `anomaly:${anomaly.id}` : null,
                    detected_at: anomaly.detected_at,
                    message: `${anomaly.machine_name || anomaly.machine_id}: ${anomaly.metric_name || anomaly.anomaly_type} anomaly detected`,
                    severity: anomaly.severity || 'warning',
                    machine_id: anomaly.machine_name || anomaly.machine_id,
                    metric: anomaly.metric_name || anomaly.anomaly_type,
                    value: anomaly.metric_value,
                    expected: anomaly.expected_value,
                    read: true
                });
                });
        } catch (error) {
            console.warn('[OVOS Widget] Failed to load active anomalies:', error);
        }
    }

    // Mark notification as read
    function markAsRead(notificationId) {
        const notification = notifications.find(n => n.id === notificationId);
        if (notification && !notification.read) {
            notification.read = true;
            unreadCount = Math.max(0, unreadCount - 1);
            saveNotifications();
            updateNotificationBadge();
            renderNotificationList();
        }
    }

    // Mark all as read
    function markAllAsRead() {
        notifications.forEach(n => n.read = true);
        unreadCount = 0;
        saveNotifications();
        updateNotificationBadge();
        renderNotificationList();
    }

    // Remove single notification
    function removeNotification(notificationId) {
        const notification = notifications.find(n => n.id === notificationId);
        if (notification && !notification.read) {
            unreadCount = Math.max(0, unreadCount - 1);
        }
        notifications = notifications.filter(n => n.id !== notificationId);
        saveNotifications();
        updateNotificationBadge();
        renderNotificationList();
    }

    // Clear all notifications
    function clearAllNotifications() {
        if (notifications.length === 0) return;
        
        if (confirm('Clear all notifications?')) {
            notifications = [];
            unreadCount = 0;
            saveNotifications();
            updateNotificationBadge();
            renderNotificationList();
        }
    }

    // Update badge (red dot)
    function updateNotificationBadge() {
        const badge = document.getElementById('notification-badge');
        if (badge) {
            if (unreadCount > 0) {
                badge.style.display = 'block';
            } else {
                badge.style.display = 'none';
            }
        }
    }

    // Toggle notification panel
    function toggleNotificationPanel() {
        const panel = document.getElementById('notification-panel');
        if (panel) {
            if (panel.style.display === 'none' || !panel.style.display) {
                panel.style.display = 'block';
                renderNotificationList();
                // Mark all as read when panel is opened
                setTimeout(() => markAllAsRead(), 1000);
            } else {
                panel.style.display = 'none';
            }
        }
    }

    // Close panel when clicking outside
    document.addEventListener('click', function(event) {
        const panel = document.getElementById('notification-panel');
        const bell = document.getElementById('notification-bell');
        
        if (panel && bell && panel.style.display === 'block') {
            if (!panel.contains(event.target) && !bell.contains(event.target)) {
                panel.style.display = 'none';
            }
        }
    });

    // Render notification list
    function renderNotificationList() {
        const listContainer = document.getElementById('notification-list');
        if (!listContainer) return;
        
        if (notifications.length === 0) {
            listContainer.innerHTML = `
                <div class="notification-empty">
                    <i class="bi bi-bell-slash"></i>
                    <p>No notifications yet</p>
                </div>
            `;
            return;
        }
        
        const html = notifications.map(notification => {
            const date = new Date(notification.timestamp);
            const timeAgo = getTimeAgo(date);
            const iconClass = notification.severity || 'warning';
            const unreadClass = notification.read ? '' : 'unread';
            
            return `
                <div class="notification-item ${unreadClass}" onclick="markAsRead('${notification.id}')">
                    <div style="display: flex; gap: 12px;">
                        <div class="notification-item-icon ${iconClass}">
                            <i class="bi bi-${getIconForSeverity(notification.severity)}"></i>
                        </div>
                        <div class="notification-item-content">
                            <div class="notification-item-message">${escapeHtml(notification.message)}</div>
                            <div class="notification-item-time">
                                <i class="bi bi-clock"></i>
                                ${timeAgo}
                            </div>
                        </div>
                        <button class="notification-item-close" onclick="event.stopPropagation(); removeNotification('${notification.id}')" title="Remove">
                            <i class="bi bi-x"></i>
                        </button>
                    </div>
                </div>
            `;
        }).join('');
        
        listContainer.innerHTML = html;
    }

    function setupNotificationPanelActions() {
        const header = document.querySelector('#notification-panel .notification-panel-header');
        if (!header) return;

        let actions = header.querySelector('.notification-panel-actions');
        if (!actions) {
            actions = document.createElement('div');
            actions.className = 'notification-panel-actions';
            header.appendChild(actions);
        }

        const clearButton = header.querySelector('.clear-all-btn');
        if (clearButton && clearButton.parentElement !== actions) {
            actions.appendChild(clearButton);
        }

        if (CONFIG.devToolsEnabled && !document.getElementById('notification-dev-warning-btn')) {
            const triggerButton = document.createElement('button');
            triggerButton.id = 'notification-dev-warning-btn';
            triggerButton.type = 'button';
            triggerButton.className = 'dev-warning-btn';
            triggerButton.setAttribute('data-dev-warning-trigger', 'true');
            triggerButton.textContent = 'Trigger Test Warning';
            triggerButton.title = 'Dev only: create a real anomaly and wait for the proactive warning flow';
            triggerButton.addEventListener('click', triggerTestProactiveWarning);
            actions.prepend(triggerButton);
        }
    }

    function setupNotificationHeaderTrigger() {
        const bellContainer = document.querySelector('.notification-bell-container');
        if (!bellContainer || !CONFIG.devToolsEnabled) return;

        if (document.getElementById('notification-dev-warning-nav-btn')) {
            return;
        }

        const triggerButton = document.createElement('button');
        triggerButton.id = 'notification-dev-warning-nav-btn';
        triggerButton.type = 'button';
        triggerButton.className = 'dev-warning-nav-btn';
        triggerButton.setAttribute('data-dev-warning-trigger', 'true');
        triggerButton.textContent = 'Trigger Test Warning';
        triggerButton.title = 'Dev only: create a real anomaly and verify the proactive warning flow';
        triggerButton.addEventListener('click', triggerTestProactiveWarning);

        bellContainer.insertAdjacentElement('afterend', triggerButton);
    }

    function setDevWarningButtonState(label, disabled) {
        document.querySelectorAll('[data-dev-warning-trigger="true"]').forEach(button => {
            button.disabled = disabled;
            button.textContent = label;
        });
    }

    async function getPreferredTestMachine() {
        const response = await fetch(`${CONFIG.machinesUrl}?is_active=true`, {
            credentials: 'same-origin'
        });

        if (!response.ok) {
            throw new Error(`Machine lookup failed with status ${response.status}`);
        }

        const machines = await response.json();
        if (!Array.isArray(machines) || machines.length === 0) {
            throw new Error('No active machines available for anomaly testing');
        }

        return machines.find(machine => /boiler-?1/i.test(machine.name || ''))
            || machines.find(machine => machine.is_active !== false)
            || machines[0];
    }

    async function triggerTestProactiveWarning() {
        if (isTriggeringDevWarning) {
            return;
        }

        isTriggeringDevWarning = true;
        setDevWarningButtonState('Triggering...', true);

        try {
            const machine = await getPreferredTestMachine();
            const expectedValue = Number(machine.rated_power_kw || 80);
            const metricValue = Number((expectedValue * 1.75).toFixed(1));
            const deviationPercent = Number((((metricValue - expectedValue) / expectedValue) * 100).toFixed(2));

            const response = await fetch(CONFIG.createAnomalyUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                credentials: 'same-origin',
                body: JSON.stringify({
                    machine_id: machine.id,
                    detected_at: new Date().toISOString(),
                    anomaly_type: 'spike',
                    severity: 'critical',
                    metric_name: 'power_kw',
                    metric_value: metricValue,
                    expected_value: expectedValue,
                    deviation_percent: deviationPercent,
                    confidence_score: 0.95,
                    is_resolved: false
                })
            });

            const responseText = await response.text();
            let payload = {};

            if (responseText) {
                try {
                    payload = JSON.parse(responseText);
                } catch (error) {
                    payload = { detail: responseText };
                }
            }

            if (!response.ok) {
                throw new Error(payload.detail || `Trigger failed with status ${response.status}`);
            }

            console.log('[OVOS Widget] Test anomaly created:', payload);

            if (isOpen) {
                addBotMessage(
                    `Test anomaly created for ${machine.name}. Waiting for proactive warning over WebSocket...`,
                    'info'
                );
            }

            setDevWarningButtonState('Waiting...', true);
            setTimeout(() => setDevWarningButtonState('Trigger Test Warning', false), 2000);
        } catch (error) {
            console.error('[OVOS Widget] Failed to trigger test anomaly:', error);

            if (isOpen) {
                addBotMessage(`Failed to trigger test anomaly: ${error.message}`, 'warning');
            }

            setDevWarningButtonState('Failed', true);
            setTimeout(() => setDevWarningButtonState('Trigger Test Warning', false), 3000);
        } finally {
            isTriggeringDevWarning = false;
        }
    }

    // Get icon for severity
    function getIconForSeverity(severity) {
        const icons = {
            'warning': 'exclamation-triangle-fill',
            'error': 'exclamation-circle-fill',
            'critical': 'exclamation-octagon-fill',
            'info': 'info-circle-fill'
        };
        return icons[severity] || 'bell-fill';
    }

    // Get time ago string
    function getTimeAgo(date) {
        const seconds = Math.floor((new Date() - date) / 1000);
        
        if (seconds < 60) return 'Just now';
        if (seconds < 3600) return Math.floor(seconds / 60) + ' min ago';
        if (seconds < 86400) return Math.floor(seconds / 3600) + ' hr ago';
        if (seconds < 604800) return Math.floor(seconds / 86400) + ' days ago';
        
        return date.toLocaleDateString();
    }

    // Escape HTML to prevent XSS
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Make functions global for onclick handlers
    window.toggleNotificationPanel = toggleNotificationPanel;
    window.clearAllNotifications = clearAllNotifications;
    window.markAsRead = markAsRead;
    window.removeNotification = removeNotification;

    // Create floating "Enable Voice" button (shown until user grants permission)
    function createEnableVoiceButton() {
        // Check if navbar button exists (for index.html with navbar)
        const navButton = document.getElementById('ovos-enable-voice-nav');
        if (navButton) {
            navButton.style.display = 'flex';
            return; // Don't create floating button if navbar button exists
        }
        
        // Check if floating button already exists
        const existingFloatBtn = document.getElementById('ovos-enable-voice');
        if (existingFloatBtn) {
            existingFloatBtn.style.display = 'flex';
            existingFloatBtn.classList.remove('hidden');
            return; // Don't create duplicate
        }
        
        // Fallback: Create floating button for pages without navbar
        const btnHTML = `
            <button id="ovos-enable-voice" class="ovos-enable-voice">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path>
                    <path d="M19 10v2a7 7 0 0 1-14 0v-2"></path>
                </svg>
                <span>Enable Voice</span>
            </button>
        `;
        const container = document.createElement('div');
        container.innerHTML = btnHTML;
        document.body.appendChild(container.firstElementChild);
    }

    // WebSocket Functions (WASABI Phase 1: Proactive Warnings)
    function connectWebSocket() {
        // Build WebSocket URL based on current page protocol
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsHost = window.location.host; // Includes port if present
        const wsFullUrl = `${wsProtocol}//${wsHost}${WS_URL}`;
        
        console.log('[OVOS Widget] Connecting to WebSocket:', wsFullUrl);
        
        try {
            ws = new WebSocket(wsFullUrl);
            
            ws.onopen = () => {
                console.log('[OVOS Widget] ✅ WebSocket connected');
                reconnectAttempts = 0; // Reset on successful connection
                updateStatus('Connected', 'green');
            };
            
            ws.onmessage = (event) => handleWebSocketMessage(event);
            
            ws.onerror = (error) => {
                console.error('[OVOS Widget] WebSocket error:', error);
            };
            
            ws.onclose = (event) => {
                console.log('[OVOS Widget] WebSocket closed:', event.code, event.reason);
                updateStatus('Reconnecting...', 'orange');
                reconnectWebSocket();
            };
        } catch (error) {
            console.error('[OVOS Widget] Failed to create WebSocket:', error);
            reconnectWebSocket();
        }
    }

    function handleWebSocketMessage(event) {
        console.log('[OVOS Widget] WebSocket message received:', event.data);
        
        try {
            const message = JSON.parse(event.data);
            console.log('[OVOS Widget] Parsed message:', message);
            console.log('[OVOS Widget] Message type:', message.type);
            console.log('[OVOS Widget] Message data:', message.data);
            
            // Handle different message types
            if (message.type === 'welcome') {
                console.log('[OVOS Widget] Connected to channel:', message.data?.channel);
            } else if (message.type === 'anomaly_detected' || message.type === 'anomaly') {
                // Handle double-nested data structure from event subscriber
                const eventData = message.data?.data || message.data;
                console.log('[OVOS Widget] Calling showProactiveWarning with data:', eventData);
                showProactiveWarning(eventData);
            } else if (message.type === 'system_alert' || message.type === 'alert') {
                const eventData = message.data?.data || message.data;
                showProactiveWarning(eventData);
            } else {
                console.log('[OVOS Widget] Unhandled message type:', message.type);
            }
        } catch (error) {
            console.error('[OVOS Widget] Failed to parse WebSocket message:', error);
        }
    }

    function reconnectWebSocket() {
        if (reconnectAttempts >= 10) {
            console.log('[OVOS Widget] Max reconnect attempts reached, stopping');
            updateStatus('Disconnected', 'red');
            return;
        }
        
        const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), MAX_RECONNECT_DELAY);
        reconnectAttempts++;
        console.log(`[OVOS Widget] Reconnecting in ${delay}ms (attempt ${reconnectAttempts}/10)`);
        
        setTimeout(connectWebSocket, delay);
    }

    function updateStatus(text, color) {
        const statusEl = document.getElementById('ovos-status');
        if (statusEl) {
            statusEl.textContent = text;
            statusEl.style.color = color || '';
        }
    }

    function showProactiveWarning(data) {
        console.log('[OVOS Widget] Showing proactive warning:', data);
        
        // Create warning message from event data
        const machine = data.machine_name || data.machine || data.machine_id || 'Unknown Machine';
        const metric = data.metric || 'status';
        const value = data.value !== undefined ? data.value : (data.current_value || 'N/A');
        const severity = data.severity || 'warning';
        
        // Format message based on available data
        let message;
        if (data.message) {
            // Use provided message if available
            message = `⚠️ ${machine}: ${data.message}`;
        } else if (data.expected) {
            // Show deviation from expected
            message = `⚠️ ${machine}: ${metric} is ${value} (expected: ${data.expected})`;
        } else {
            // Basic format
            message = `⚠️ ${machine}: ${metric} is ${value}`;
        }
        
        // Add to notification bell
        addNotification({
            backend_id: data.id ? `anomaly:${data.id}` : null,
            timestamp: data.timestamp || data.detected_at,
            message: message,
            severity: severity,
            machine_id: machine,
            metric: metric,
            value: value,
            expected: data.expected
        });
        
        // Add message to chat (even if widget is closed)
        addBotMessage(message, severity);
        
        // Show notification popup if widget is closed
        if (!isOpen) {
            showNotificationPopup(message, severity);
        }
        
        // Play alert sound if audio enabled
        if (audioEnabled) {
            playAlertSound();
        }
    }

    function showNotificationPopup(message, severity) {
        // Create popup toast notification
        const toast = document.createElement('div');
        toast.className = 'ovos-toast ovos-toast-' + severity;
        toast.innerHTML = `
            <div class="ovos-toast-icon">⚠️</div>
            <div class="ovos-toast-content">
                <div class="ovos-toast-title">Proactive Warning</div>
                <div class="ovos-toast-message">${message}</div>
            </div>
            <button class="ovos-toast-close">×</button>
        `;
        
        document.body.appendChild(toast);
        
        // Auto-dismiss after 10 seconds
        setTimeout(() => {
            toast.classList.add('ovos-toast-hide');
            setTimeout(() => toast.remove(), 300);
        }, 10000);
        
        // Close button
        toast.querySelector('.ovos-toast-close').addEventListener('click', () => {
            toast.classList.add('ovos-toast-hide');
            setTimeout(() => toast.remove(), 300);
        });
        
        // Click to open widget
        toast.addEventListener('click', (e) => {
            if (!e.target.classList.contains('ovos-toast-close')) {
                if (!isOpen) toggleWidget();
                toast.classList.add('ovos-toast-hide');
                setTimeout(() => toast.remove(), 300);
            }
        });
    }

    function playAlertSound() {
        // Simple beep using Web Audio API
        try {
            const audioContext = new (window.AudioContext || window.webkitAudioContext)();
            const oscillator = audioContext.createOscillator();
            const gainNode = audioContext.createGain();
            
            oscillator.connect(gainNode);
            gainNode.connect(audioContext.destination);
            
            oscillator.frequency.value = 800; // Hz
            gainNode.gain.value = 0.3; // Volume
            
            oscillator.start(audioContext.currentTime);
            oscillator.stop(audioContext.currentTime + 0.2);
        } catch (error) {
            console.error('[OVOS Widget] Failed to play alert sound:', error);
        }
    }

    function addBotMessage(text, className) {
        const messagesDiv = document.getElementById('ovos-messages');
        if (!messagesDiv) return;
        
        const messageDiv = document.createElement('div');
        messageDiv.className = 'ovos-message ovos-bot' + (className ? ' ovos-' + className : '');
        messageDiv.innerHTML = `<div class="ovos-bubble">${text}</div>`;
        messagesDiv.appendChild(messageDiv);
        messagesDiv.scrollTop = messagesDiv.scrollHeight;
    }

    // Create widget HTML
    function createWidget() {
        const widgetHTML = `
            <div id="ovos-voice-widget" class="ovos-closed">
                <!-- Toggle Button -->
                <button id="ovos-toggle" class="ovos-toggle" aria-label="Open OVOS voice assistant" title="OVOS Voice Assistant">
                    <svg class="ovos-icon-open" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path>
                        <path d="M19 10v2a7 7 0 0 1-14 0v-2"></path>
                        <line x1="12" y1="19" x2="12" y2="23"></line>
                        <line x1="8" y1="23" x2="16" y2="23"></line>
                    </svg>
                    <svg class="ovos-icon-close" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="display:none">
                        <path d="M18 6L6 18M6 6l12 12"></path>
                    </svg>
                </button>

                <!-- Chat Window -->
                <div id="ovos-window" class="ovos-window">
                    <!-- Header -->
                    <div class="ovos-header">
                        <div class="ovos-header-info">
                            <div class="ovos-avatar">
                                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path>
                                    <path d="M19 10v2a7 7 0 0 1-14 0v-2"></path>
                                </svg>
                            </div>
                            <div>
                                <div class="ovos-title">${CONFIG.title}</div>
                                <div class="ovos-status" id="ovos-status">${CONFIG.subtitle}</div>
                            </div>
                        </div>
                        <button id="ovos-minimize" class="ovos-minimize" aria-label="Minimize">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M18 6L6 18M6 6l12 12"></path>
                            </svg>
                        </button>
                    </div>

                    <div class="ovos-content">
                        <!-- Messages -->
                        <div id="ovos-messages" class="ovos-messages">
                            <div class="ovos-message ovos-bot">
                                <div class="ovos-bubble">${CONFIG.welcomeMessage}</div>
                            </div>
                            <!-- Quick Reply Buttons in Chat -->
                            <div class="ovos-quick-replies">
                                <button class="ovos-quick-btn" data-query="factory overview">Overview</button>
                                <button class="ovos-quick-btn" data-query="any anomalies today?">Anomalies</button>
                                <button class="ovos-quick-btn" data-query="top energy consumers">Top Consumers</button>
                            </div>
                        </div>

                        <aside id="ovos-insights-panel" class="ovos-insights-panel" aria-hidden="true">
                            <div class="ovos-insights-header">
                                <div>
                                    <div class="ovos-insights-kicker">Extra Context</div>
                                    <div id="ovos-insights-title" class="ovos-insights-title">Operational insights</div>
                                    <div id="ovos-insights-subtitle" class="ovos-insights-subtitle"></div>
                                </div>
                                <button id="ovos-insights-close" class="ovos-insights-close" aria-label="Close extra insights">×</button>
                            </div>
                            <div id="ovos-insights-body" class="ovos-insights-body">
                                <div class="ovos-insights-empty">Ask about a machine, anomalies, or factory performance to expand this view.</div>
                            </div>
                        </aside>
                    </div>

                    <!-- Controls (Audio + Wake Word) -->
                    <div class="ovos-controls">
                        <button id="ovos-wakeword-toggle" class="ovos-wakeword-toggle" title="Enable 'Jarvis' wake word">Jarvis</button>
                        <button id="ovos-audio-toggle" class="ovos-audio-toggle" title="Toggle audio">🔊</button>
                    </div>

                    <!-- Input -->
                    <div class="ovos-input-container">
                        <button id="ovos-mic" class="ovos-mic" aria-label="Voice input" title="Click to speak">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path>
                                <path d="M19 10v2a7 7 0 0 1-14 0v-2"></path>
                                <line x1="12" y1="19" x2="12" y2="23"></line>
                            </svg>
                        </button>
                        <input 
                            type="text" 
                            id="ovos-input" 
                            class="ovos-input" 
                            placeholder="${CONFIG.placeholder}"
                            autocomplete="off"
                        >
                        <button id="ovos-send" class="ovos-send" aria-label="Send">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <line x1="22" y1="2" x2="11" y2="13"></line>
                                <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
                            </svg>
                        </button>
                    </div>
                </div>
            </div>
        `;

        const container = document.createElement('div');
        container.innerHTML = widgetHTML;
        document.body.appendChild(container.firstElementChild);
    }

    // Create widget styles
    function createStyles() {
        const styles = `
            /* Floating Enable Voice Button */
            .ovos-enable-voice {
                position: fixed;
                bottom: 100px;
                right: 20px;
                z-index: 10000;
                display: flex;
                align-items: center;
                gap: 8px;
                padding: 10px 16px;
                background: linear-gradient(135deg, #7c3aed 0%, #6d28d9 100%);
                color: white;
                border: none;
                border-radius: 25px;
                font-size: 13px;
                font-weight: 600;
                cursor: pointer;
                box-shadow: 0 4px 16px rgba(124, 58, 237, 0.4);
                animation: ovos-enable-pulse 2s infinite;
                transition: all 0.3s ease;
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            }

            .ovos-enable-voice:hover {
                transform: scale(1.05);
                box-shadow: 0 6px 24px rgba(124, 58, 237, 0.5);
            }

            @keyframes ovos-enable-pulse {
                0%, 100% { box-shadow: 0 4px 16px rgba(124, 58, 237, 0.4); }
                50% { box-shadow: 0 4px 24px rgba(124, 58, 237, 0.6), 0 0 0 8px rgba(124, 58, 237, 0.1); }
            }

            .ovos-enable-voice.loading {
                pointer-events: none;
                opacity: 0.8;
            }

            .ovos-enable-voice.hidden {
                display: none;
            }

            /* Wake Word Active Indicator */
            .ovos-wakeword-indicator {
                position: fixed;
                top: 20px;
                right: 20px;
                z-index: 10000;
                display: flex;
                align-items: center;
                gap: 6px;
                padding: 8px 14px;
                background: rgba(16, 185, 129, 0.9);
                color: white;
                border-radius: 20px;
                font-size: 12px;
                font-weight: 500;
                box-shadow: 0 2px 12px rgba(16, 185, 129, 0.3);
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                cursor: pointer;
            }

            .ovos-wakeword-indicator .dot {
                width: 8px;
                height: 8px;
                background: white;
                border-radius: 50%;
                animation: ovos-dot-pulse 1.5s infinite;
            }

            @keyframes ovos-dot-pulse {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.4; }
            }

            #ovos-voice-widget {
                position: fixed;
                bottom: 90px;
                right: 20px;
                z-index: 9999;
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            }

            .ovos-toggle {
                width: 52px;
                height: 52px;
                border-radius: 50%;
                background: linear-gradient(135deg, #10B981 0%, #059669 100%);
                border: none;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                box-shadow: 0 4px 16px rgba(16, 185, 129, 0.4);
                transition: all 0.3s ease;
                color: white;
            }

            .ovos-toggle:hover {
                transform: scale(1.1);
                box-shadow: 0 6px 24px rgba(16, 185, 129, 0.5);
            }

            #ovos-voice-widget,
            #ovos-voice-widget button,
            #ovos-voice-widget input {
                font-family: "Manrope", "Avenir Next", "Segoe UI Variable", sans-serif;
            }

            .ovos-window {
                position: absolute;
                bottom: 65px;
                right: 0;
                width: 380px;
                height: 500px;
                background: linear-gradient(180deg, rgba(255, 255, 255, 0.98) 0%, rgba(244, 253, 249, 0.98) 100%);
                border: 1px solid rgba(16, 185, 129, 0.14);
                border-radius: 22px;
                box-shadow: 0 18px 60px rgba(6, 78, 59, 0.18);
                display: none;
                flex-direction: column;
                overflow: hidden;
                animation: ovos-slide-up 0.3s ease;
                transition: width 0.35s ease, height 0.35s ease, box-shadow 0.35s ease;
            }

            .ovos-window.ovos-expanded {
                width: 728px;
                box-shadow: 0 26px 72px rgba(5, 150, 105, 0.2);
            }

            @keyframes ovos-slide-up {
                from { opacity: 0; transform: translateY(20px); }
                to { opacity: 1; transform: translateY(0); }
            }

            .ovos-closed .ovos-window { display: none; }
            .ovos-open .ovos-window { display: flex; }
            .ovos-open .ovos-icon-open { display: none; }
            .ovos-open .ovos-icon-close { display: block !important; }

            .ovos-header {
                background: linear-gradient(135deg, #10B981 0%, #059669 100%);
                color: white;
                padding: 15px 18px;
                display: flex;
                align-items: center;
                justify-content: space-between;
            }

            .ovos-header-info {
                display: flex;
                align-items: center;
                gap: 12px;
            }

            .ovos-avatar {
                width: 36px;
                height: 36px;
                background: rgba(255, 255, 255, 0.2);
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
            }

            .ovos-title {
                font-weight: 700;
                font-size: 15px;
                letter-spacing: -0.01em;
            }

            .ovos-status {
                font-size: 11px;
                opacity: 0.85;
            }

            .ovos-status.online { color: #bbf7d0; }
            .ovos-status.offline { color: #fca5a5; }

            .ovos-minimize {
                background: rgba(255, 255, 255, 0.1);
                border: none;
                border-radius: 8px;
                padding: 6px;
                cursor: pointer;
                color: white;
                transition: background 0.2s;
            }

            .ovos-minimize:hover {
                background: rgba(255, 255, 255, 0.2);
            }

            .ovos-content {
                flex: 1;
                min-height: 0;
                display: flex;
                background: linear-gradient(180deg, #f5fdf9 0%, #ecfdf5 100%);
            }

            .ovos-messages {
                flex: 1;
                overflow-y: auto;
                padding: 16px;
                display: flex;
                flex-direction: column;
                gap: 10px;
                background: linear-gradient(180deg, rgba(240, 253, 244, 0.75) 0%, rgba(236, 253, 245, 0.95) 100%);
                min-width: 0;
            }

            .ovos-insights-panel {
                width: 0;
                opacity: 0;
                transform: translateX(18px);
                overflow: hidden;
                background: linear-gradient(180deg, #f8fffb 0%, #ecfdf5 100%);
                border-left: 1px solid rgba(16, 185, 129, 0.18);
                transition: width 0.32s ease, opacity 0.25s ease, transform 0.32s ease;
                display: flex;
                flex-direction: column;
                pointer-events: none;
                min-width: 0;
            }

            .ovos-window.ovos-expanded .ovos-insights-panel {
                width: 320px;
                opacity: 1;
                transform: translateX(0);
                pointer-events: auto;
            }

            .ovos-insights-header {
                padding: 18px 18px 16px;
                display: flex;
                align-items: flex-start;
                justify-content: space-between;
                gap: 12px;
                border-bottom: 1px solid rgba(16, 185, 129, 0.12);
                background: rgba(255, 255, 255, 0.74);
                backdrop-filter: blur(10px);
            }

            .ovos-insights-header > div {
                min-width: 0;
            }

            .ovos-insights-kicker {
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 0.12em;
                text-transform: uppercase;
                color: #059669;
                margin-bottom: 5px;
            }

            .ovos-insights-title {
                font-size: 18px;
                font-weight: 800;
                color: #064e3b;
                line-height: 1.15;
                letter-spacing: -0.02em;
                overflow-wrap: anywhere;
            }

            .ovos-insights-subtitle {
                margin-top: 4px;
                font-size: 11px;
                line-height: 1.5;
                color: #4b5563;
                overflow-wrap: anywhere;
            }

            .ovos-insights-close {
                width: 28px;
                height: 28px;
                border: none;
                border-radius: 999px;
                background: rgba(16, 185, 129, 0.08);
                color: #047857;
                font-size: 18px;
                line-height: 1;
                cursor: pointer;
                transition: transform 0.2s ease, background 0.2s ease;
                flex-shrink: 0;
            }

            .ovos-insights-close:hover {
                background: rgba(16, 185, 129, 0.16);
                transform: scale(1.05);
            }

            .ovos-insights-body {
                flex: 1;
                overflow-y: auto;
                padding: 16px 18px 18px;
                display: flex;
                flex-direction: column;
                gap: 14px;
                scrollbar-width: thin;
                scrollbar-color: rgba(16, 185, 129, 0.36) transparent;
            }

            .ovos-insights-body::-webkit-scrollbar {
                width: 8px;
            }

            .ovos-insights-body::-webkit-scrollbar-thumb {
                background: rgba(16, 185, 129, 0.26);
                border-radius: 999px;
            }

            .ovos-insights-body::-webkit-scrollbar-track {
                background: transparent;
            }

            .ovos-insights-empty {
                padding: 14px 15px;
                border-radius: 18px;
                background: rgba(255, 255, 255, 0.8);
                color: #4b5563;
                font-size: 12px;
                line-height: 1.55;
                box-shadow: 0 8px 18px rgba(16, 185, 129, 0.08);
            }

            .ovos-insight-spotlight {
                padding: 16px 16px 15px;
                border-radius: 20px;
                border: 1px solid rgba(16, 185, 129, 0.14);
                background: linear-gradient(135deg, rgba(220, 252, 231, 0.92) 0%, rgba(255, 255, 255, 0.96) 100%);
                box-shadow: 0 14px 28px rgba(5, 150, 105, 0.1);
            }

            .ovos-insight-spotlight.tone-info {
                background: linear-gradient(135deg, rgba(219, 234, 254, 0.92) 0%, rgba(255, 255, 255, 0.96) 100%);
            }

            .ovos-insight-spotlight.tone-warning {
                background: linear-gradient(135deg, rgba(254, 243, 199, 0.94) 0%, rgba(255, 255, 255, 0.96) 100%);
            }

            .ovos-insight-spotlight.tone-danger {
                background: linear-gradient(135deg, rgba(254, 226, 226, 0.94) 0%, rgba(255, 255, 255, 0.96) 100%);
            }

            .ovos-insight-spotlight-kicker {
                font-size: 10px;
                font-weight: 800;
                letter-spacing: 0.12em;
                text-transform: uppercase;
                color: rgba(6, 78, 59, 0.72);
                margin-bottom: 8px;
            }

            .ovos-insight-spotlight-title {
                font-size: 27px;
                font-weight: 800;
                line-height: 1.02;
                letter-spacing: -0.04em;
                color: #0f172a;
                overflow-wrap: anywhere;
                word-break: break-word;
            }

            .ovos-insight-spotlight-detail {
                margin-top: 10px;
                font-size: 12px;
                line-height: 1.55;
                color: #334155;
                overflow-wrap: anywhere;
            }

            .ovos-insight-metrics {
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: 12px;
            }

            .ovos-insight-metric {
                padding: 14px 14px 12px;
                border-radius: 18px;
                background: rgba(255, 255, 255, 0.9);
                box-shadow: 0 8px 18px rgba(5, 150, 105, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.6);
                min-height: 114px;
                display: flex;
                flex-direction: column;
                justify-content: space-between;
                gap: 10px;
                min-width: 0;
                overflow: hidden;
            }

            .ovos-insight-metric-label {
                font-size: 10px;
                font-weight: 800;
                letter-spacing: 0.08em;
                text-transform: uppercase;
                color: #6b7280;
                line-height: 1.4;
            }

            .ovos-insight-metric-value {
                min-width: 0;
                color: #111827;
            }

            .ovos-insight-metric-primary {
                display: block;
                font-size: 26px;
                font-weight: 800;
                line-height: 1.02;
                letter-spacing: -0.04em;
                overflow-wrap: anywhere;
                word-break: break-word;
            }

            .ovos-insight-metric-value.is-compact .ovos-insight-metric-primary {
                font-size: 22px;
            }

            .ovos-insight-metric-value.is-text .ovos-insight-metric-primary {
                font-size: 17px;
                line-height: 1.18;
                letter-spacing: -0.02em;
            }

            .ovos-insight-metric-unit {
                display: block;
                margin-top: 6px;
                font-size: 10px;
                font-weight: 800;
                letter-spacing: 0.12em;
                text-transform: uppercase;
                color: #64748b;
            }

            .ovos-insight-metric.tone-good {
                background: linear-gradient(180deg, rgba(209, 250, 229, 0.95) 0%, rgba(255, 255, 255, 0.95) 100%);
            }

            .ovos-insight-metric.tone-warning {
                background: linear-gradient(180deg, rgba(254, 243, 199, 0.95) 0%, rgba(255, 255, 255, 0.95) 100%);
            }

            .ovos-insight-metric.tone-danger {
                background: linear-gradient(180deg, rgba(254, 226, 226, 0.95) 0%, rgba(255, 255, 255, 0.95) 100%);
            }

            .ovos-insight-metric.tone-info {
                background: linear-gradient(180deg, rgba(219, 234, 254, 0.95) 0%, rgba(255, 255, 255, 0.95) 100%);
            }

            .ovos-insight-badges {
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
            }

            .ovos-insight-badge {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                padding: 7px 11px;
                border-radius: 999px;
                font-size: 11px;
                font-weight: 700;
                line-height: 1;
            }

            .ovos-insight-badge.tone-good {
                background: rgba(16, 185, 129, 0.14);
                color: #047857;
            }

            .ovos-insight-badge.tone-warning {
                background: rgba(245, 158, 11, 0.16);
                color: #92400e;
            }

            .ovos-insight-badge.tone-danger {
                background: rgba(239, 68, 68, 0.14);
                color: #b91c1c;
            }

            .ovos-insight-badge.tone-info {
                background: rgba(59, 130, 246, 0.16);
                color: #1d4ed8;
            }

            .ovos-insight-badge.tone-neutral {
                background: rgba(17, 24, 39, 0.08);
                color: #374151;
            }

            .ovos-insight-lines {
                display: flex;
                flex-direction: column;
                gap: 10px;
            }

            .ovos-insight-line {
                padding: 12px 13px;
                border-radius: 16px;
                background: rgba(255, 255, 255, 0.92);
                color: #1f2937;
                font-size: 12px;
                line-height: 1.55;
                box-shadow: 0 8px 18px rgba(5, 150, 105, 0.08);
            }

            .ovos-insight-links {
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
                margin-top: auto;
            }

            .ovos-insight-link {
                display: inline-flex;
                align-items: center;
                gap: 6px;
                padding: 9px 11px;
                border-radius: 14px;
                background: rgba(16, 185, 129, 0.12);
                color: #065f46;
                font-size: 11px;
                font-weight: 800;
                text-decoration: none;
                transition: transform 0.2s ease, background 0.2s ease;
            }

            .ovos-insight-link:hover {
                background: rgba(16, 185, 129, 0.18);
                transform: translateY(-1px);
            }

            .ovos-message {
                display: flex;
                flex-direction: column;
                max-width: 85%;
            }

            .ovos-user { align-self: flex-end; }
            .ovos-bot { align-self: flex-start; }

            .ovos-bubble {
                padding: 10px 14px;
                border-radius: 14px;
                font-size: 13px;
                line-height: 1.5;
                word-wrap: break-word;
                white-space: pre-wrap;
                position: relative;
            }

            .ovos-user .ovos-bubble {
                background: linear-gradient(135deg, #10B981 0%, #059669 100%);
                color: white;
                border-bottom-right-radius: 4px;
            }

            .ovos-bot .ovos-bubble {
                background: white;
                color: #1f2937;
                border-bottom-left-radius: 4px;
                box-shadow: 0 2px 6px rgba(0, 0, 0, 0.06);
            }

            .ovos-bubble.ovos-streaming::after {
                content: '';
                display: inline-block;
                width: 2px;
                height: 1em;
                margin-left: 3px;
                vertical-align: text-bottom;
                background: #10b981;
                animation: ovos-stream-caret 0.85s steps(1) infinite;
            }

            @keyframes ovos-stream-caret {
                0%, 49% { opacity: 1; }
                50%, 100% { opacity: 0; }
            }

            /* Quick Reply Buttons inside Chat */
            .ovos-quick-replies {
                padding: 12px 16px 8px;
                display: flex;
                gap: 8px;
                flex-wrap: wrap;
                align-items: flex-start;
            }

            .ovos-quick-btn {
                padding: 6px 12px;
                border: 1px solid #d1fae5;
                border-radius: 16px;
                background: #ecfdf5;
                font-size: 12px;
                cursor: pointer;
                transition: all 0.2s;
                color: #065f46;
            }

            .ovos-quick-btn:hover {
                background: #10B981;
                border-color: #10B981;
                color: white;
                transform: translateY(-1px);
                box-shadow: 0 2px 4px rgba(16, 185, 129, 0.2);
            }

            /* Controls Bar (Wake Word + Audio) */
            .ovos-controls {
                padding: 8px 12px;
                background: #f9fafb;
                border-top: 1px solid #e5e7eb;
                display: flex;
                gap: 8px;
                align-items: center;
            }

            .ovos-wakeword-toggle {
                padding: 6px 12px;
                border: 1px solid #d1fae5;
                border-radius: 16px;
                background: #ecfdf5;
                font-size: 11px;
                cursor: pointer;
                transition: all 0.2s;
                color: #065f46;
            }

            .ovos-wakeword-toggle.active {
                background: #7c3aed;
                border-color: #7c3aed;
                color: white;
                animation: ovos-wakeword-pulse 2s infinite;
            }

            @keyframes ovos-wakeword-pulse {
                0%, 100% { box-shadow: 0 0 0 0 rgba(124, 58, 237, 0.4); }
                50% { box-shadow: 0 0 0 8px rgba(124, 58, 237, 0); }
            }

            .ovos-wakeword-toggle:hover {
                transform: scale(1.05);
            }

            .ovos-audio-toggle {
                padding: 6px 10px;
                border: 1px solid #d1fae5;
                border-radius: 16px;
                background: #ecfdf5;
                font-size: 14px;
                cursor: pointer;
                transition: all 0.2s;
                margin-left: auto;
            }

            .ovos-audio-toggle.muted {
                background: #fee2e2;
                border-color: #fecaca;
            }

            .ovos-audio-toggle:hover {
                transform: scale(1.1);
            }

            .ovos-input-container {
                padding: 12px;
                background: white;
                border-top: 1px solid #e5e7eb;
                display: flex;
                gap: 10px;
                align-items: center;
            }

            .ovos-mic {
                width: 40px;
                height: 40px;
                border-radius: 50%;
                background: #f0fdf4;
                border: 2px solid #10B981;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                color: #10B981;
                transition: all 0.2s;
                flex-shrink: 0;
            }

            .ovos-mic:hover {
                background: #10B981;
                color: white;
            }

            .ovos-mic.listening {
                background: #dc2626;
                border-color: #dc2626;
                color: white;
                animation: ovos-pulse 1s infinite;
            }

            @keyframes ovos-pulse {
                0%, 100% { transform: scale(1); }
                50% { transform: scale(1.1); }
            }

            .ovos-mic:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }

            .ovos-input {
                flex: 1;
                padding: 10px 14px;
                border: 1px solid #d1fae5;
                border-radius: 20px;
                font-size: 13px;
                outline: none;
                transition: border-color 0.2s;
            }

            .ovos-input:focus {
                border-color: #10B981;
            }

            .ovos-send {
                width: 40px;
                height: 40px;
                border-radius: 50%;
                background: linear-gradient(135deg, #10B981 0%, #059669 100%);
                border: none;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                transition: all 0.2s;
            }

            .ovos-send:hover { transform: scale(1.05); }
            .ovos-send:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }

            .ovos-typing {
                display: flex;
                align-items: center;
                gap: 4px;
                padding: 10px 14px;
                background: white;
                border-radius: 14px;
                border-bottom-left-radius: 4px;
                box-shadow: 0 2px 6px rgba(0, 0, 0, 0.06);
            }

            .ovos-typing-dot {
                width: 6px;
                height: 6px;
                background: #10B981;
                border-radius: 50%;
                animation: ovos-typing 1.4s infinite ease-in-out;
            }

            .ovos-typing-dot:nth-child(1) { animation-delay: 0s; }
            .ovos-typing-dot:nth-child(2) { animation-delay: 0.2s; }
            .ovos-typing-dot:nth-child(3) { animation-delay: 0.4s; }

            @keyframes ovos-typing {
                0%, 60%, 100% { transform: translateY(0); }
                30% { transform: translateY(-4px); }
            }

            .ovos-error {
                background: #fef2f2 !important;
                color: #dc2626 !important;
                border-left: 3px solid #dc2626;
            }

            .ovos-latency {
                font-size: 9px;
                color: #9ca3af;
                margin-top: 3px;
                text-align: right;
            }

            @media (max-width: 700px) {
                .ovos-window {
                    width: calc(100vw - 32px);
                    height: calc(100vh - 160px);
                    bottom: 70px;
                    right: -12px;
                }

                .ovos-window.ovos-expanded {
                    width: calc(100vw - 32px);
                    height: calc(100vh - 120px);
                }

                .ovos-content {
                    flex-direction: column;
                }

                .ovos-insights-panel {
                    width: 100%;
                    max-height: 0;
                    opacity: 0;
                    transform: translateY(14px);
                    border-left: none;
                    border-top: 1px solid rgba(16, 185, 129, 0.18);
                    transition: max-height 0.32s ease, opacity 0.25s ease, transform 0.32s ease;
                }

                .ovos-window.ovos-expanded .ovos-insights-panel {
                    width: 100%;
                    max-height: 280px;
                    opacity: 1;
                    transform: translateY(0);
                }

                .ovos-insight-metrics {
                    grid-template-columns: 1fr 1fr;
                }

                .ovos-insight-spotlight-title {
                    font-size: 23px;
                }

                .ovos-insight-metric-primary {
                    font-size: 23px;
                }
            }
        `;

        const styleSheet = document.createElement('style');
        styleSheet.textContent = styles;
        document.head.appendChild(styleSheet);
    }

    function toggleWidget() {
        const widget = document.getElementById('ovos-voice-widget');
        isOpen = !isOpen;
        widget.className = isOpen ? 'ovos-open' : 'ovos-closed';
        if (isOpen) {
            document.getElementById('ovos-input').focus();
            checkHealth();
        }
    }

    async function addMessage(text, isUser = false, isError = false, latencyMs = null, ttsLatencyMs = null, options = {}) {
        const { stream = false } = options;
        const container = document.getElementById('ovos-messages');
        const msgDiv = document.createElement('div');
        msgDiv.className = `ovos-message ${isUser ? 'ovos-user' : 'ovos-bot'}`;
        
        const bubble = document.createElement('div');
        bubble.className = `ovos-bubble ${isError ? 'ovos-error' : ''}`;
        msgDiv.appendChild(bubble);
        container.appendChild(msgDiv);

        if (stream) {
            await streamMessageText(bubble, text, container);
        } else {
            bubble.textContent = text;
            container.scrollTop = container.scrollHeight;
        }
        
        if (!isUser && latencyMs !== null) {
            const latency = document.createElement('div');
            latency.className = 'ovos-latency';
            let latencyText = `${latencyMs}ms`;
            if (ttsLatencyMs && ttsLatencyMs > 0) {
                latencyText += ` (TTS: ${ttsLatencyMs}ms)`;
            }
            latency.textContent = latencyText;
            msgDiv.appendChild(latency);
        }
        
        container.scrollTop = container.scrollHeight;
    }

    function finishActiveMessageAnimation() {
        if (!activeMessageAnimation) {
            return;
        }

        const animation = activeMessageAnimation;
        animation.finished = true;
        animation.bubble.textContent = animation.fullText;
        animation.bubble.classList.remove('ovos-streaming');
        animation.container.scrollTop = animation.container.scrollHeight;

        if (animation.timeoutId) {
            window.clearTimeout(animation.timeoutId);
            animation.timeoutId = null;
        }

        if (animation.resume) {
            const resume = animation.resume;
            animation.resume = null;
            resume();
        }

        activeMessageAnimation = null;
    }

    function stopActiveInsightsAnimation() {
        if (!activeInsightsAnimation) {
            return;
        }

        activeInsightsAnimation.cancelled = true;
        activeInsightsAnimation.timeouts.forEach(timeoutId => window.clearTimeout(timeoutId));
        activeInsightsAnimation.resolvers.forEach(resolve => resolve());
        activeInsightsAnimation = null;
    }

    function collapseInsightsPanel() {
        const windowEl = document.getElementById('ovos-window');
        const panel = document.getElementById('ovos-insights-panel');
        const title = document.getElementById('ovos-insights-title');
        const subtitle = document.getElementById('ovos-insights-subtitle');
        const body = document.getElementById('ovos-insights-body');

        stopActiveInsightsAnimation();

        if (!windowEl || !panel || !title || !subtitle || !body) {
            return;
        }

        windowEl.classList.remove('ovos-expanded');
        panel.setAttribute('aria-hidden', 'true');
        title.textContent = 'Operational insights';
        subtitle.textContent = '';
        body.innerHTML = '<div class="ovos-insights-empty">Ask about a machine, anomalies, or factory performance to expand this view.</div>';
    }

    function hasInsightsContent(insights) {
        if (!insights || typeof insights !== 'object') {
            return false;
        }

        const spotlight = insights.spotlight && typeof insights.spotlight === 'object' ? insights.spotlight : null;
        const metrics = Array.isArray(insights.summary_metrics) ? insights.summary_metrics.filter(Boolean) : [];
        const badges = Array.isArray(insights.status_badges) ? insights.status_badges.filter(Boolean) : [];
        const lines = Array.isArray(insights.secondary_lines) ? insights.secondary_lines.filter(Boolean) : [];
        const links = Array.isArray(insights.links) ? insights.links.filter(Boolean) : [];

        return Boolean(insights.title || spotlight || metrics.length || badges.length || lines.length || links.length);
    }

    function formatInsightValue(value) {
        if (typeof value === 'number' && Number.isFinite(value)) {
            const valueText = String(value);
            const fractional = valueText.includes('.') ? valueText.split('.')[1].length : 0;
            const maxFractionDigits = Math.min(fractional, 2);
            return new Intl.NumberFormat(undefined, {
                minimumFractionDigits: 0,
                maximumFractionDigits: maxFractionDigits
            }).format(value);
        }

        return String(value ?? '');
    }

    function getInsightMetricValueClass(metricText, unit) {
        const classNames = ['ovos-insight-metric-value'];
        if (metricText.length > 10) {
            classNames.push('is-compact');
        }
        if (/[A-Za-z]/.test(metricText) || metricText.length > 14) {
            classNames.push('is-text');
        }
        if (unit) {
            classNames.push('has-unit');
        }
        return classNames.join(' ');
    }

    function cloneInsightItems(items) {
        return Array.isArray(items)
            ? items.filter(Boolean).map(item => (item && typeof item === 'object' ? { ...item } : item))
            : [];
    }

    function extractLeadingPercentage(line) {
        if (typeof line !== 'string') {
            return null;
        }

        const match = line.match(/\(([\d.]+)%\)/);
        return match ? Number.parseFloat(match[1]) : null;
    }

    function normalizeInsightsPayload(insights, rawData) {
        if ((!insights || typeof insights !== 'object') && (!rawData || typeof rawData !== 'object')) {
            return null;
        }

        const normalized = {
            ...(insights && typeof insights === 'object' ? insights : {}),
            summary_metrics: cloneInsightItems(insights?.summary_metrics),
            status_badges: cloneInsightItems(insights?.status_badges),
            secondary_lines: Array.isArray(insights?.secondary_lines) ? insights.secondary_lines.filter(Boolean) : [],
            links: cloneInsightItems(insights?.links)
        };

        if (insights?.spotlight && typeof insights.spotlight === 'object') {
            normalized.spotlight = { ...insights.spotlight };
        }

        if (normalized.panel_type === 'ranking') {
            const metrics = normalized.summary_metrics;
            const topMachineIndex = metrics.findIndex(metric => String(metric?.label || '').toLowerCase() === 'top machine');
            const topMachineMetric = topMachineIndex >= 0 ? metrics[topMachineIndex] : null;
            const topValueMetric = metrics.find(metric => String(metric?.label || '').toLowerCase() === 'top value');
            const leaderShareMetric = metrics.find(metric => String(metric?.label || '').toLowerCase() === 'leader share');

            if (!normalized.spotlight && topMachineMetric?.value) {
                let leaderShare = leaderShareMetric?.value;
                if (leaderShare == null) {
                    leaderShare = extractLeadingPercentage(normalized.secondary_lines[0]);
                }

                const detailParts = [];
                if (topValueMetric?.value != null) {
                    detailParts.push(`${formatInsightValue(topValueMetric.value)} ${topValueMetric.unit || ''}`.trim());
                }
                if (leaderShare != null) {
                    detailParts.push(`${formatInsightValue(leaderShare)}% of tracked load`);
                }

                normalized.spotlight = {
                    kicker: 'Top consumer',
                    title: String(topMachineMetric.value),
                    detail: detailParts.join(' · '),
                    tone: 'info'
                };
            }

            if (topMachineIndex >= 0) {
                normalized.summary_metrics = metrics.filter((_, index) => index !== topMachineIndex);
            }
        }

        if (normalized.panel_type === 'factory_overview' && rawData && typeof rawData === 'object') {
            const fallbackMetrics = [
                { label: 'Total Energy', value: rawData.total_energy, unit: 'kWh', tone: 'neutral' },
                { label: 'Live Rate', value: rawData.energy_per_hour, unit: 'kWh/h', tone: 'info' },
                { label: 'Active Today', value: rawData.active_machines_today, unit: null, tone: 'good' },
                { label: 'Estimated Cost', value: rawData.estimated_cost, unit: 'USD', tone: 'warning' }
            ].filter(metric => metric.value !== undefined && metric.value !== null);

            if (normalized.summary_metrics.length < 3 && fallbackMetrics.length) {
                normalized.summary_metrics = fallbackMetrics;
            }

            if (!normalized.spotlight && rawData.energy_per_hour != null) {
                const detailParts = [];
                if (rawData.active_machines_today != null) {
                    detailParts.push(`${formatInsightValue(rawData.active_machines_today)} active machines`);
                }
                if (rawData.total_anomalies != null) {
                    detailParts.push(`${formatInsightValue(rawData.total_anomalies)} alerts tracked`);
                }
                if (rawData.cost_per_day != null) {
                    detailParts.push(`$${formatInsightValue(rawData.cost_per_day)}/day est.`);
                }

                normalized.spotlight = {
                    kicker: 'Factory pulse',
                    title: `${formatInsightValue(rawData.energy_per_hour)} kWh/h`,
                    detail: detailParts.join(' · '),
                    tone: rawData.total_anomalies > 0 ? 'warning' : 'info'
                };
            }

            const looksGeneric = normalized.secondary_lines.length <= 1
                && normalized.secondary_lines[0]
                && normalized.secondary_lines[0].includes('Factory-wide summary');

            if (!normalized.secondary_lines.length || looksGeneric) {
                const lines = [];
                if (rawData.peak_power != null || rawData.avg_power != null) {
                    const parts = [];
                    if (rawData.peak_power != null) {
                        parts.push(`Peak power reached ${formatInsightValue(rawData.peak_power)} kW`);
                    }
                    if (rawData.avg_power != null) {
                        parts.push(`average power held at ${formatInsightValue(rawData.avg_power)} kW`);
                    }
                    if (parts.length) {
                        lines.push(`${parts.join('. ')}.`);
                    }
                }
                if (rawData.estimated_cost != null || rawData.cost_per_day != null) {
                    const parts = [];
                    if (rawData.estimated_cost != null) {
                        parts.push(`Estimated spend is $${formatInsightValue(rawData.estimated_cost)}`);
                    }
                    if (rawData.cost_per_day != null) {
                        parts.push(`roughly $${formatInsightValue(rawData.cost_per_day)} per day`);
                    }
                    if (parts.length) {
                        lines.push(`${parts.join(' with ')}.`);
                    }
                }
                if (rawData.carbon_footprint != null) {
                    lines.push(`Carbon footprint estimate is ${formatInsightValue(rawData.carbon_footprint)} kilograms.`);
                }
                if (rawData.total_readings != null || rawData.readings_per_minute != null) {
                    const parts = [];
                    if (rawData.total_readings != null) {
                        parts.push(`${formatInsightValue(rawData.total_readings)} readings captured`);
                    }
                    if (rawData.readings_per_minute != null) {
                        parts.push(`${formatInsightValue(rawData.readings_per_minute)} readings per minute`);
                    }
                    if (parts.length) {
                        lines.push(`Telemetry stream processed ${parts.join(' at ')}.`);
                    }
                }

                normalized.secondary_lines = lines.slice(0, 4);
            }

            if (rawData.active_machines_today != null && !normalized.status_badges.some(badge => String(badge?.label || '').toLowerCase().includes('active'))) {
                normalized.status_badges.push({ label: `${formatInsightValue(rawData.active_machines_today)} active machines`, tone: 'info' });
            }
            if (rawData.total_anomalies === 0 && !normalized.status_badges.some(badge => String(badge?.label || '').toLowerCase().includes('alert'))) {
                normalized.status_badges.push({ label: 'No active alerts', tone: 'good' });
            } else if (rawData.total_anomalies > 0 && !normalized.status_badges.some(badge => String(badge?.label || '').toLowerCase().includes('alert'))) {
                normalized.status_badges.push({ label: `${formatInsightValue(rawData.total_anomalies)} alerts logged`, tone: 'warning' });
            }
        }

        return normalized;
    }

    function renderInsightSpotlight(spotlight) {
        if (!spotlight || typeof spotlight !== 'object' || !spotlight.title) {
            return '';
        }

        return `
            <div class="ovos-insight-spotlight tone-${escapeHtml(spotlight.tone || 'info')}">
                ${spotlight.kicker ? `<div class="ovos-insight-spotlight-kicker">${escapeHtml(spotlight.kicker)}</div>` : ''}
                <div class="ovos-insight-spotlight-title">${escapeHtml(String(spotlight.title))}</div>
                ${spotlight.detail ? `<div class="ovos-insight-spotlight-detail">${escapeHtml(String(spotlight.detail))}</div>` : ''}
            </div>
        `;
    }

    function renderInsightMetrics(metrics) {
        if (!metrics.length) {
            return '';
        }

        return `
            <div class="ovos-insight-metrics">
                ${metrics.map(metric => {
                    const metricValue = formatInsightValue(metric.value);
                    const valueClassName = getInsightMetricValueClass(metricValue, metric.unit);

                    return `
                    <div class="ovos-insight-metric tone-${escapeHtml(metric.tone || 'neutral')}">
                        <div class="ovos-insight-metric-label">${escapeHtml(metric.label || 'Metric')}</div>
                        <div class="${valueClassName}">
                            <span class="ovos-insight-metric-primary">${escapeHtml(metricValue)}</span>
                            ${metric.unit ? `<span class="ovos-insight-metric-unit">${escapeHtml(metric.unit)}</span>` : ''}
                        </div>
                    </div>
                `;}).join('')}
            </div>
        `;
    }

    function renderInsightBadges(badges) {
        if (!badges.length) {
            return '';
        }

        return `
            <div class="ovos-insight-badges">
                ${badges.map(badge => `
                    <div class="ovos-insight-badge tone-${escapeHtml(badge.tone || 'neutral')}">${escapeHtml(badge.label || '')}</div>
                `).join('')}
            </div>
        `;
    }

    function getInsightLinkLabel(link) {
        if (!link || typeof link !== 'object') {
            return '';
        }

        return String(link.label || link.title || link.text || link.name || '').trim();
    }

    function getInsightLinkHref(link) {
        if (!link || typeof link !== 'object') {
            return '#';
        }

        return String(link.href || link.url || link.download_url || '#').trim() || '#';
    }

    function isSuppressedInsightLink(link) {
        return /^open reports?$/i.test(getInsightLinkLabel(link));
    }

    function renderInsightLinks(links) {
        const visibleLinks = Array.isArray(links)
            ? links.filter(Boolean).filter(link => !isSuppressedInsightLink(link))
            : [];

        if (!visibleLinks.length) {
            return '';
        }

        return `
            <div class="ovos-insight-links">
                ${visibleLinks.map(link => `
                    <a class="ovos-insight-link" href="${escapeHtml(getInsightLinkHref(link))}">${escapeHtml(getInsightLinkLabel(link) || 'Open')}</a>
                `).join('')}
            </div>
        `;
    }

    async function streamInsightLine(element, text, animation) {
        const tokens = text.match(/\S+\s*/g) || [text];
        if (tokens.length <= 1) {
            element.textContent = text;
            return;
        }

        const delayMs = Math.min(55, Math.max(18, Math.round(900 / tokens.length)));
        element.textContent = '';

        for (const token of tokens) {
            if (!activeInsightsAnimation || animation.cancelled) {
                return;
            }

            element.textContent += token;

            await new Promise(resolve => {
                animation.resolvers.push(resolve);
                const timeoutId = window.setTimeout(() => {
                    animation.resolvers = animation.resolvers.filter(item => item !== resolve);
                    animation.timeouts = animation.timeouts.filter(id => id !== timeoutId);
                    resolve();
                }, delayMs);
                animation.timeouts.push(timeoutId);
            });
        }
    }

    async function renderInsightsPanel(insights, rawData) {
        const windowEl = document.getElementById('ovos-window');
        const panel = document.getElementById('ovos-insights-panel');
        const title = document.getElementById('ovos-insights-title');
        const subtitle = document.getElementById('ovos-insights-subtitle');
        const body = document.getElementById('ovos-insights-body');

        if (!windowEl || !panel || !title || !subtitle || !body) {
            return;
        }

        const normalizedInsights = normalizeInsightsPayload(insights, rawData);

        if (!hasInsightsContent(normalizedInsights)) {
            collapseInsightsPanel();
            return;
        }

        stopActiveInsightsAnimation();

        const spotlight = normalizedInsights.spotlight && typeof normalizedInsights.spotlight === 'object' ? normalizedInsights.spotlight : null;
        const metrics = Array.isArray(normalizedInsights.summary_metrics) ? normalizedInsights.summary_metrics.filter(Boolean) : [];
        const badges = Array.isArray(normalizedInsights.status_badges) ? normalizedInsights.status_badges.filter(Boolean) : [];
        const lines = Array.isArray(normalizedInsights.secondary_lines) ? normalizedInsights.secondary_lines.filter(Boolean).slice(0, 4) : [];
        const links = Array.isArray(normalizedInsights.links)
            ? normalizedInsights.links
                .filter(Boolean)
                .filter(link => !isSuppressedInsightLink(link))
                .slice(0, 2)
            : [];

        title.textContent = normalizedInsights.title || 'Operational insights';
        subtitle.textContent = normalizedInsights.subtitle || '';
        body.innerHTML = `
            ${renderInsightSpotlight(spotlight)}
            ${renderInsightMetrics(metrics)}
            ${renderInsightBadges(badges)}
            <div id="ovos-insight-lines" class="ovos-insight-lines"></div>
            ${renderInsightLinks(links)}
        `;

        windowEl.classList.add('ovos-expanded');
        panel.setAttribute('aria-hidden', 'false');

        const lineContainer = document.getElementById('ovos-insight-lines');
        if (!lineContainer) {
            return;
        }

        if (!lines.length) {
            lineContainer.innerHTML = '<div class="ovos-insight-line">Live operational context is available for this response.</div>';
            return;
        }

        const animation = {
            cancelled: false,
            timeouts: [],
            resolvers: []
        };
        activeInsightsAnimation = animation;

        for (const line of lines) {
            if (!activeInsightsAnimation || animation.cancelled) {
                return;
            }

            const lineElement = document.createElement('div');
            lineElement.className = 'ovos-insight-line';
            lineContainer.appendChild(lineElement);
            await streamInsightLine(lineElement, line, animation);
        }

        if (activeInsightsAnimation === animation) {
            activeInsightsAnimation = null;
        }
    }

    function getStreamingDelay(wordCount) {
        if (wordCount <= 1) {
            return STREAMING_MIN_DELAY_MS;
        }

        return Math.min(
            STREAMING_MAX_DELAY_MS,
            Math.max(STREAMING_MIN_DELAY_MS, Math.round(STREAMING_TARGET_TOTAL_MS / wordCount))
        );
    }

    async function streamMessageText(bubble, text, container) {
        const tokens = text.match(/\S+\s*/g) || [text];
        if (tokens.length <= 1) {
            bubble.textContent = text;
            return;
        }

        finishActiveMessageAnimation();

        const animation = {
            bubble,
            container,
            fullText: text,
            finished: false,
            timeoutId: null,
            resume: null
        };

        const delayMs = getStreamingDelay(tokens.length);
        activeMessageAnimation = animation;
        bubble.classList.add('ovos-streaming');
        bubble.textContent = '';

        try {
            for (const token of tokens) {
                if (animation.finished) {
                    return;
                }

                bubble.textContent += token;
                container.scrollTop = container.scrollHeight;

                await new Promise(resolve => {
                    animation.resume = resolve;
                    animation.timeoutId = window.setTimeout(resolve, delayMs);
                });

                animation.resume = null;
                animation.timeoutId = null;
            }
        } finally {
            bubble.textContent = text;
            bubble.classList.remove('ovos-streaming');
            container.scrollTop = container.scrollHeight;

            if (activeMessageAnimation === animation) {
                activeMessageAnimation = null;
            }
        }
    }

    function showTyping() {
        const container = document.getElementById('ovos-messages');
        const div = document.createElement('div');
        div.id = 'ovos-typing';
        div.className = 'ovos-message ovos-bot';
        div.innerHTML = `<div class="ovos-typing"><div class="ovos-typing-dot"></div><div class="ovos-typing-dot"></div><div class="ovos-typing-dot"></div></div>`;
        container.appendChild(div);
        container.scrollTop = container.scrollHeight;
    }

    function hideTyping() {
        const el = document.getElementById('ovos-typing');
        if (el) el.remove();
    }

    async function checkHealth() {
        const statusEl = document.getElementById('ovos-status');
        try {
            const res = await fetch(CONFIG.healthUrl);
            if (res.ok) {
                const data = await res.json();
                // Check bridge_reachable (nginx proxy) or messagebus_connected (direct)
                if (data.bridge_reachable || data.messagebus_connected) {
                    statusEl.textContent = 'Connected';
                    statusEl.className = 'ovos-status online';
                } else {
                    statusEl.textContent = 'OVOS Offline';
                    statusEl.className = 'ovos-status offline';
                }
            } else {
                statusEl.textContent = 'Bridge Offline';
                statusEl.className = 'ovos-status offline';
            }
        } catch (e) {
            statusEl.textContent = 'Offline';
            statusEl.className = 'ovos-status offline';
        }
    }

    async function sendMessage(text) {
        if (!text.trim()) return;

        finishActiveMessageAnimation();
        collapseInsightsPanel();
        
        // Cancel previous request if running
        if (isLoading && abortController) {
            console.log('🚫 Cancelling previous request...');
            abortController.abort();
            hideTyping();
            addMessage('(Previous request cancelled)', false, false);
            
            // Call REST bridge cancel endpoint with OLD session ID
            const oldSessionId = sessionId;
            try {
                const cancelUrl = CONFIG.apiUrl.replace('/query', '/cancel') + `?session_id=${oldSessionId}`;
                await fetch(cancelUrl, { method: 'POST' });
            } catch (e) {
                console.warn('Cancel request failed (non-critical):', e);
            }
            
            // Wait 1 second for cleanup to complete
            await new Promise(resolve => setTimeout(resolve, 1000));
        }

        isLoading = true;
        abortController = new AbortController();
        const input = document.getElementById('ovos-input');
        const sendBtn = document.getElementById('ovos-send');
        
        input.disabled = true;
        sendBtn.disabled = true;

        addMessage(text, true);
        input.value = '';
        showTyping();

        stopActivePlayback();

        // Generate unique session ID for this query
        const querySessionId = sessionId + '_' + Date.now();

        try {
            const res = await fetch(CONFIG.apiUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    text: text, 
                    session_id: querySessionId
                }),
                signal: abortController.signal
            });

            hideTyping();
            const data = await res.json();

            if (data.success && data.response) {
                const responseRender = addMessage(
                    data.response,
                    false,
                    false,
                    data.latency_ms,
                    data.tts_latency_ms,
                    { stream: true }
                );
                
                // Play audio if available and enabled
                if (audioEnabled) {
                    if (data.audio_base64) {
                        // Option 1: Server-side TTS (OVOS generated audio)
                        playAudio(data.audio_base64, data.audio_format || 'wav');
                    } else if (window.speechSynthesis) {
                        // Option 2: Fallback to browser TTS (Web Speech API)
                        speakText(data.response);
                    }
                }

                await responseRender;
                renderInsightsPanel(data.insights, data.data);
                
                // Trigger PDF download if present (for report generation queries)
                // V2: REST bridge returns pdf_download object with URL instead of base64
                console.log('🔍 Checking for PDF download:', {
                    has_pdf_download: !!data.pdf_download,
                    is_ready: data.pdf_download?.ready,
                    full_data: data.pdf_download
                });
                
                if (data.pdf_download && data.pdf_download.ready) {
                    console.log('📄 PDF download available:', data.pdf_download.filename);
                    console.log('📄 Calling downloadPDFFromURL...');
                    downloadPDFFromURL(data.pdf_download.download_url, data.pdf_download.filename);
                    addMessage(`📄 Downloading: ${data.pdf_download.filename} (${data.pdf_download.file_size_kb.toFixed(1)} KB)`, false, false);
                } else if (data.pdf_base64 && data.pdf_filename) {
                    // Legacy: Fallback to base64 download (backward compatibility)
                    console.log('📄 Triggering PDF download (base64):', data.pdf_filename);
                    downloadPDF(data.pdf_base64, data.pdf_filename);
                }
            } else if (data.error) {
                collapseInsightsPanel();
                addMessage(data.error, false, true);
            } else {
                collapseInsightsPanel();
                addMessage('No response received.', false, true);
            }
        } catch (err) {
            hideTyping();
            if (err.name === 'AbortError') {
                console.log('✅ Request aborted successfully');
                // Don't show error - already showed "(cancelled)" message
            } else {
                console.error('OVOS error:', err);
                collapseInsightsPanel();
                addMessage('Connection error. Is OVOS REST Bridge running?', false, true);
            }
        } finally {
            isLoading = false;
            abortController = null;
            input.disabled = false;
            sendBtn.disabled = false;
            input.focus();
        }
    }

    function playAudio(base64Data, format) {
        try {
            // Map format to proper MIME type
            const mimeType = format === 'mp3' ? 'audio/mpeg' : `audio/${format}`;
            const audio = new Audio(`data:${mimeType};base64,${base64Data}`);
            currentAudio = audio;
            
            audio.onended = () => {
                currentAudio = null;
            };
            
            audio.onerror = (e) => {
                console.error('Audio playback error:', e);
                currentAudio = null;
            };
            
            audio.play().catch(err => {
                console.warn('Audio autoplay blocked:', err);
                // Browser may block autoplay - user interaction required
            });
        } catch (err) {
            console.error('Failed to create audio:', err);
        }
    }

    function stopActivePlayback() {
        if (currentAudio) {
            try {
                currentAudio.pause();
                currentAudio.currentTime = 0;
                currentAudio.removeAttribute('src');
                currentAudio.load();
            } catch (err) {
                console.warn('Failed to stop current audio cleanly:', err);
            }
            currentAudio = null;
        }

        if (window.speechSynthesis) {
            window.speechSynthesis.cancel();
        }
    }

    /**
     * Speak text using browser's Web Speech API (fallback TTS)
     * Used when OVOS doesn't provide audio
     */
    function speakText(text) {
        try {
            // Cancel any ongoing speech
            window.speechSynthesis.cancel();
            
            const utterance = new SpeechSynthesisUtterance(text);
            utterance.rate = 0.95;     // Slightly slower for clarity
            utterance.pitch = 1.0;     // Normal pitch
            utterance.volume = 1.0;    // Full volume
            utterance.lang = 'en-US';  // English US
            
            // Try to use the best quality voice available
            const voices = window.speechSynthesis.getVoices();
            
            // Priority order: Google UK Male > Microsoft Natural > Other good voices
            const voicePriority = [
                v => v.name.includes('Google UK English Male'),
                v => v.name.includes('Google') && v.name.includes('Male'),
                v => v.name.includes('Microsoft') && v.name.includes('Natural'),
                v => v.name.includes('Microsoft') && (v.name.includes('Guy') || v.name.includes('David')),
                v => v.name.includes('Google') && v.lang === 'en-GB',
                v => v.name.includes('Google') && v.lang === 'en-US',
                v => !v.name.includes('Female') && v.lang.startsWith('en-')
            ];
            
            let selectedVoice = null;
            for (const matcher of voicePriority) {
                selectedVoice = voices.find(matcher);
                if (selectedVoice) break;
            }
            
            if (selectedVoice) {
                utterance.voice = selectedVoice;
                console.log('🎤 Using voice:', selectedVoice.name);
            }
            
            utterance.onerror = (e) => {
                console.error('Speech synthesis error:', e);
            };
            
            window.speechSynthesis.speak(utterance);
            console.log('🔊 Speaking with browser TTS:', text.substring(0, 50));
            
        } catch (err) {
            console.error('Failed to speak text:', err);
        }
    }

    /**
     * Download PDF from base64 data
     * Called automatically when OVOS returns a report
     */
    function downloadPDF(base64Data, filename) {
        try {
            // Decode base64 to binary
            const binaryString = atob(base64Data);
            const bytes = new Uint8Array(binaryString.length);
            for (let i = 0; i < binaryString.length; i++) {
                bytes[i] = binaryString.charCodeAt(i);
            }
            
            // Create blob and trigger download
            const blob = new Blob([bytes], { type: 'application/pdf' });
            const url = URL.createObjectURL(blob);
            
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            
            // Cleanup
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            
            console.log(`✅ PDF downloaded: ${filename}`);
        } catch (err) {
            console.error('Failed to download PDF:', err);
            addMessage(`PDF download failed: ${err.message}`, false, true);
        }
    }

    /**
     * Download PDF from URL (V2 report system)
     * Fetches PDF from EnMS API and triggers browser download
     * @param {string} downloadUrl - Full URL to PDF download endpoint
     * @param {string} filename - Name for downloaded file
     */
    async function downloadPDFFromURL(downloadUrl, filename) {
        try {
            console.log(`📄 Original PDF URL: ${downloadUrl}`);
            
            // CRITICAL FIX: Rewrite URLs to go through nginx proxy
            // This avoids CORS/mixed content issues (HTTPS page loading HTTP resource)
            // Cases:
            // 1. Relative path: /api/v1/reports/... → /api/analytics/api/v1/reports/...
            // 2. Absolute with :8001: http://host:8001/api/v1/... → /api/analytics/api/v1/...
            // 3. Docker service name: http://enms-analytics:8001/... → /api/analytics/...
            let proxiedUrl = downloadUrl;
            
            if (downloadUrl.startsWith('/api/v1/')) {
                // Relative path from API
                proxiedUrl = '/api/analytics' + downloadUrl;
                console.log(`📄 Rewritten relative path to nginx proxy: ${proxiedUrl}`);
            } else if (downloadUrl.includes(':8001') || downloadUrl.includes('enms-analytics')) {
                // Absolute URL or Docker service name
                try {
                    const urlObj = new URL(downloadUrl);
                    proxiedUrl = '/api/analytics' + urlObj.pathname;
                    console.log(`📄 Rewritten absolute URL to nginx proxy: ${proxiedUrl}`);
                } catch (e) {
                    // If URL parsing fails, try direct fetch (fallback)
                    console.warn(`⚠️ Could not parse URL, using as-is: ${downloadUrl}`);
                }
            }
            
            const response = await fetch(proxiedUrl);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const blob = await response.blob();
            console.log(`✅ PDF fetched: ${(blob.size / 1024).toFixed(1)} KB`);
            
            // Create download link
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            
            // Cleanup
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            
            console.log(`✅ PDF downloaded successfully: ${filename}`);
        } catch (err) {
            console.error('❌ Failed to download PDF from URL:', err);
            addMessage(`PDF download failed: ${err.message}`, false, true);
        }
    }

    function toggleAudio() {
        audioEnabled = !audioEnabled;
        const btn = document.getElementById('ovos-audio-toggle');
        btn.textContent = audioEnabled ? '🔊' : '🔇';
        btn.classList.toggle('muted', !audioEnabled);
        btn.title = audioEnabled ? 'Audio enabled (click to mute)' : 'Audio muted (click to enable)';
        
        if (!audioEnabled) {
            stopActivePlayback();
        }
    }

    // Speech Recognition (Browser STT)
    let recognition = null;
    let isListening = false;

    function initSpeechRecognition() {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        
        if (!SpeechRecognition) {
            console.warn('Speech recognition not supported in this browser');
            const micBtn = document.getElementById('ovos-mic');
            if (micBtn) {
                micBtn.style.display = 'none';
            }
            return false;
        }

        recognition = new SpeechRecognition();
        recognition.continuous = false;
        recognition.interimResults = true;
        recognition.lang = 'en-US';

        recognition.onstart = () => {
            isListening = true;
            const micBtn = document.getElementById('ovos-mic');
            micBtn.classList.add('listening');
            micBtn.title = 'Listening... (click to stop)';
            document.getElementById('ovos-input').placeholder = 'Listening...';
        };

        recognition.onend = () => {
            isListening = false;
            const micBtn = document.getElementById('ovos-mic');
            micBtn.classList.remove('listening');
            micBtn.title = 'Click to speak';
            document.getElementById('ovos-input').placeholder = CONFIG.placeholder;
            
            // Restart wake word listening if enabled
            if (wakeWordEnabled && wakeWordRecognition) {
                // Reset indicator text
                const indicator = document.getElementById('ovos-wakeword-indicator');
                if (indicator) {
                    indicator.style.background = 'rgba(16, 185, 129, 0.9)';
                    indicator.querySelector('span').textContent = 'Say "Jarvis"';
                }
                
                // Restart wake word after a short delay
                setTimeout(() => {
                    if (wakeWordEnabled && !isListening) {
                        try {
                            wakeWordRecognition.start();
                        } catch (e) {}
                    }
                }, 500);
            }
        };

        recognition.onresult = (event) => {
            const input = document.getElementById('ovos-input');
            let finalTranscript = '';
            let interimTranscript = '';

            for (let i = event.resultIndex; i < event.results.length; i++) {
                const transcript = event.results[i][0].transcript;
                if (event.results[i].isFinal) {
                    finalTranscript += transcript;
                } else {
                    interimTranscript += transcript;
                }
            }

            // Show interim results in input
            input.value = finalTranscript || interimTranscript;

            // Auto-send when final result received
            if (finalTranscript) {
                setTimeout(() => {
                    sendMessage(finalTranscript);
                }, 300);
            }
        };

        recognition.onerror = (event) => {
            console.error('Speech recognition error:', event.error);
            isListening = false;
            const micBtn = document.getElementById('ovos-mic');
            micBtn.classList.remove('listening');
            
            if (event.error === 'not-allowed') {
                addMessage('Microphone access denied. Please allow microphone access in your browser settings.', false, true);
            } else if (event.error !== 'aborted') {
                addMessage(`Voice input error: ${event.error}`, false, true);
            }
        };

        return true;
    }

    function toggleListening() {
        if (!recognition) {
            if (!initSpeechRecognition()) {
                addMessage('Voice input not supported in this browser. Try Chrome or Edge.', false, true);
                return;
            }
        }

        if (isListening) {
            recognition.stop();
        } else {
            stopActivePlayback();
            try {
                recognition.start();
            } catch (e) {
                console.error('Failed to start recognition:', e);
            }
        }
    }

    // =========================================================================
    // Wake Word Detection (Using Web Speech API - No external dependencies)
    // =========================================================================
    
    let wakeWordRecognition = null;
    let lastWakeWordTime = 0;  // Debounce wake word detection
    
    function initWakeWord() {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        
        if (!SpeechRecognition) {
            addMessage('Wake word requires a browser with Speech Recognition (Chrome, Edge).', false, true);
            return false;
        }

        try {
            wakeWordRecognition = new SpeechRecognition();
            wakeWordRecognition.continuous = true;  // Keep listening
            wakeWordRecognition.interimResults = true;  // Get partial results
            wakeWordRecognition.lang = 'en-US';
            
            wakeWordRecognition.onresult = (event) => {
                // Check all results for wake word
                for (let i = event.resultIndex; i < event.results.length; i++) {
                    const transcript = event.results[i][0].transcript.toLowerCase();
                    
                    // Check for wake word
                    if (transcript.includes('jarvis') || transcript.includes('travis') || transcript.includes('jervis')) {
                        // Debounce - ignore if triggered within last 3 seconds
                        const now = Date.now();
                        if (now - lastWakeWordTime < 3000) {
                            console.log('Wake word debounced (already triggered recently)');
                            return;
                        }
                        lastWakeWordTime = now;
                        
                        console.log('🎯 Wake word detected in:', transcript);
                        
                        // Stop wake word listening temporarily
                        wakeWordRecognition.stop();
                        
                        // Trigger the wake word callback
                        onWakeWordDetected();
                        return;
                    }
                }
            };
            
            wakeWordRecognition.onend = () => {
                // Auto-restart if wake word is enabled (unless we're in query mode)
                if (wakeWordEnabled && !isListening) {
                    setTimeout(() => {
                        if (wakeWordEnabled && !isListening) {
                            try {
                                wakeWordRecognition.start();
                            } catch (e) {
                                // Ignore - might already be started
                            }
                        }
                    }, 100);
                }
            };
            
            wakeWordRecognition.onerror = (event) => {
                if (event.error === 'not-allowed') {
                    addMessage('Microphone access denied. Please allow mic access.', false, true);
                    wakeWordEnabled = false;
                    updateWakeWordUI(false);
                } else if (event.error !== 'aborted' && event.error !== 'no-speech') {
                    console.warn('Wake word recognition error:', event.error);
                }
            };
            
            // Start listening
            wakeWordRecognition.start();
            console.log('✅ Wake word "Jarvis" listening started (Web Speech API)');
            return true;
            
        } catch (error) {
            console.error('Failed to initialize wake word:', error);
            addMessage(`Wake word error: ${error.message}`, false, true);
            return false;
        }
    }
    
    function stopWakeWord() {
        if (wakeWordRecognition) {
            try {
                wakeWordRecognition.stop();
            } catch (e) {}
            wakeWordRecognition = null;
        }
    }
    
    function onWakeWordDetected() {
        console.log('🎯 Wake word activated!');

        stopActivePlayback();
        
        // Abort any in-flight request
        if (isLoading && abortController) {
            console.log('🚫 Interrupting current request...');
            abortController.abort();
            hideTyping();
        }
        
        // Visual feedback on indicator
        const indicator = document.getElementById('ovos-wakeword-indicator');
        if (indicator) {
            indicator.style.background = 'rgba(124, 58, 237, 0.95)';
            indicator.querySelector('span').textContent = 'Listening...';
        }
        
        // Open widget
        if (!isOpen) {
            toggleWidget();
        }
        
        // Add feedback message (only if not cancelling)
        if (!isLoading) {
            addMessage('Jarvis activated! Listening for your command...', false, false);
        }
        
        // Start query listening
        setTimeout(() => {
            if (!isListening) {
                toggleListening();
            }
        }, 300);
    }
    
    function updateWakeWordUI(enabled) {
        const wakeBtn = document.getElementById('ovos-wakeword-toggle');
        const indicator = document.getElementById('ovos-wakeword-indicator');
        const enableBtn = document.getElementById('ovos-enable-voice');
        
        if (enabled) {
            if (wakeBtn) {
                wakeBtn.classList.add('active');
                wakeBtn.title = 'Wake word active - say "Jarvis" (click to disable)';
            }
            if (enableBtn) enableBtn.classList.add('hidden');
        } else {
            if (wakeBtn) {
                wakeBtn.classList.remove('active');
                wakeBtn.title = 'Enable "Jarvis" wake word';
            }
            if (indicator) indicator.remove();
        }
    }

    // One-time enable function - grants permission and starts background listening
    async function enableVoiceAssistant() {
        const enableBtn = document.getElementById('ovos-enable-voice-nav') || document.getElementById('ovos-enable-voice');
        if (!enableBtn) return;
        
        enableBtn.classList.add('loading');
        enableBtn.innerHTML = '<span>Enabling...</span>';
        
        try {
            // Initialize wake word (this requests mic permission)
            const success = initWakeWord();
            
            if (success) {
                voicePermissionGranted = true;
                wakeWordEnabled = true;
                
                // Hide enable button
                enableBtn.classList.add('hidden');
                
                // Show persistent indicator
                showWakeWordIndicator();
                
                // Update toggle button in widget
                updateWakeWordUI(true);
                
                console.log('✅ Voice assistant enabled - say "Jarvis" anytime!');
            } else {
                enableBtn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path><path d="M19 10v2a7 7 0 0 1-14 0v-2"></path></svg><span>Enable Voice</span>';
                enableBtn.classList.remove('loading');
            }
        } catch (error) {
            console.error('Failed to enable voice:', error);
            enableBtn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path><path d="M19 10v2a7 7 0 0 1-14 0v-2"></path></svg><span>Enable Voice</span>';
            enableBtn.classList.remove('loading');
        }
    }

    function showWakeWordIndicator() {
        // Hide enable buttons if exists (don't remove - just hide)
        const navBtn = document.getElementById('ovos-enable-voice-nav');
        const floatBtn = document.getElementById('ovos-enable-voice');
        if (navBtn) navBtn.style.display = 'none';
        if (floatBtn) floatBtn.style.display = 'none';
        
        // Create indicator
        const indicatorHTML = `
            <div id="ovos-wakeword-indicator" class="ovos-wakeword-indicator" title="Click to disable voice assistant">
                <div class="dot"></div>
                <span>Say "Jarvis"</span>
            </div>
        `;
        const container = document.createElement('div');
        container.innerHTML = indicatorHTML;
        document.body.appendChild(container.firstElementChild);
        
        // Click to disable
        document.getElementById('ovos-wakeword-indicator').addEventListener('click', disableVoiceAssistant);
    }

    function disableVoiceAssistant() {
        // Stop wake word recognition
        stopWakeWord();
        wakeWordEnabled = false;
        voicePermissionGranted = false;
        
        // Remove indicator
        const indicator = document.getElementById('ovos-wakeword-indicator');
        if (indicator) indicator.remove();
        
        // Show enable button again (will show existing button, not create new one)
        createEnableVoiceButton();
        const enableBtn = document.getElementById('ovos-enable-voice-nav') || document.getElementById('ovos-enable-voice');
        if (enableBtn) {
            // Remove old listener to avoid duplicates
            enableBtn.removeEventListener('click', enableVoiceAssistant);
            enableBtn.addEventListener('click', enableVoiceAssistant);
        }
        
        // Update widget button
        updateWakeWordUI(false);
        
        console.log('🔇 Voice assistant disabled');
    }

    function toggleWakeWord() {
        const btn = document.getElementById('ovos-wakeword-toggle');
        
        if (wakeWordEnabled) {
            // Disable wake word
            stopWakeWord();
            wakeWordEnabled = false;
            btn.classList.remove('active');
            btn.textContent = 'Jarvis';
            btn.title = 'Enable "Jarvis" wake word';
            console.log('Wake word disabled');
            
            // Also remove indicator if present
            const indicator = document.getElementById('ovos-wakeword-indicator');
            if (indicator) indicator.remove();
            
            // Show enable button again (will show existing button, not create new one)
            createEnableVoiceButton();
            const enableBtn = document.getElementById('ovos-enable-voice-nav') || document.getElementById('ovos-enable-voice');
            if (enableBtn) {
                // Remove old listener to avoid duplicates
                enableBtn.removeEventListener('click', enableVoiceAssistant);
                enableBtn.addEventListener('click', enableVoiceAssistant);
            }
            
        } else {
            // Enable wake word
            btn.textContent = 'Enabling...';
            const success = initWakeWord();
            
            if (success) {
                wakeWordEnabled = true;
                btn.classList.add('active');
                btn.textContent = 'Jarvis';
                btn.title = 'Wake word active - say "Jarvis" (click to disable)';
                addMessage('Wake word enabled! Say "Jarvis" to activate voice input.', false, false);
                
                // Hide enable button if visible
                const enableBtn = document.getElementById('ovos-enable-voice');
                if (enableBtn) enableBtn.classList.add('hidden');
                
                // Show indicator
                if (!document.getElementById('ovos-wakeword-indicator')) {
                    showWakeWordIndicator();
                }
            } else {
                btn.textContent = 'Jarvis';
            }
        }
    }

    function init() {
        createStyles();
        createWidget();
        setupNotificationPanelActions();
        setupNotificationHeaderTrigger();
        
        // Load notifications from localStorage
        loadNotifications();
        syncNotificationsFromBackend();
        
        // Create floating "Enable Voice" button (for one-time permission)
        createEnableVoiceButton();
        
        // Log available voices for debugging
        if (window.speechSynthesis) {
            window.speechSynthesis.onvoiceschanged = () => {
                const voices = window.speechSynthesis.getVoices();
                console.log('🎤 Available TTS voices:', voices.map(v => `${v.name} (${v.lang})`));
            };
            // Trigger immediately if voices already loaded
            if (window.speechSynthesis.getVoices().length > 0) {
                const voices = window.speechSynthesis.getVoices();
                console.log('🎤 Available TTS voices:', voices.map(v => `${v.name} (${v.lang})`));
            }
        }

        document.getElementById('ovos-toggle').addEventListener('click', toggleWidget);
        document.getElementById('ovos-minimize').addEventListener('click', toggleWidget);
        
        document.getElementById('ovos-send').addEventListener('click', () => {
            sendMessage(document.getElementById('ovos-input').value);
        });

        document.getElementById('ovos-input').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') sendMessage(e.target.value);
        });

        document.querySelectorAll('.ovos-quick-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const query = btn.getAttribute('data-query');
                if (query) sendMessage(query);
            });
        });

        document.getElementById('ovos-audio-toggle').addEventListener('click', toggleAudio);
        document.getElementById('ovos-insights-close').addEventListener('click', collapseInsightsPanel);
        
        // Mic button for voice input
        document.getElementById('ovos-mic').addEventListener('click', toggleListening);
        
        // Wake word toggle (inside widget)
        document.getElementById('ovos-wakeword-toggle').addEventListener('click', toggleWakeWord);
        
        // Enable voice button (navbar or floating - one-time permission)
        const enableBtn = document.getElementById('ovos-enable-voice-nav') || document.getElementById('ovos-enable-voice');
        if (enableBtn) {
            enableBtn.addEventListener('click', enableVoiceAssistant);
        }
        
        // Initialize speech recognition
        initSpeechRecognition();

        // Connect to WebSocket for proactive warnings (WASABI Phase 1)
        connectWebSocket();

        console.log('✅ EnMS OVOS Voice Widget loaded (hands-free ready - click "Enable Voice" to start)');
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
