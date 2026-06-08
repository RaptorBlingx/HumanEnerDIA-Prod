/**
 * EnMS Analytics - WebSocket Client Utility
 * ===========================================
 * Handles WebSocket connections with auto-reconnect, heartbeat, and error handling.
 * 
 * Author: EnMS Team
 * Phase: 4 - Session 5 - Real-Time Updates
 * Date: October 15, 2025
 */

class WebSocketClient {
    /**
     * Create a WebSocket client
     * @param {string} endpoint - WebSocket endpoint path (e.g., '/api/v1/ws/dashboard')
     * @param {function} onMessage - Callback for incoming messages
     * @param {function} onConnect - Optional callback on connection
     * @param {function} onDisconnect - Optional callback on disconnection
     */
    constructor(endpoint, onMessage, onConnect = null, onDisconnect = null) {
        this.endpoint = endpoint;
        this.onMessage = onMessage;
        this.onConnect = onConnect || (() => {});
        this.onDisconnect = onDisconnect || (() => {});
        
        this.ws = null;
        this.clientId = this.generateClientId();
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 10;
        this.reconnectDelay = 1000; // Start with 1 second
        this.maxReconnectDelay = 30000; // Max 30 seconds
        this.isConnected = false;
        this.shouldReconnect = true;
        this.heartbeatInterval = null;
        this.heartbeatTimer = 30000; // 30 seconds
        
        // Bind methods to maintain context
        this.connect = this.connect.bind(this);
        this.disconnect = this.disconnect.bind(this);
        this.send = this.send.bind(this);
        this.handleOpen = this.handleOpen.bind(this);
        this.handleMessage = this.handleMessage.bind(this);
        this.handleError = this.handleError.bind(this);
        this.handleClose = this.handleClose.bind(this);
        
        // Auto-connect on initialization
        this.connect();
    }
    
    /**
     * Generate a unique client ID
     * @returns {string} Unique client identifier
     */
    generateClientId() {
        return `client-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    }
    
    /**
     * Get the full WebSocket URL
     * @returns {string} WebSocket URL
     */
    getWebSocketUrl() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = window.location.hostname;
        const port = window.location.port || '8080'; // Use same port as browser (nginx)
        
        // Add /api/analytics prefix to match nginx routing
        let endpoint = this.endpoint;
        if (!endpoint.startsWith('/api/analytics')) {
            endpoint = '/api/analytics' + endpoint;
        }
        
        return `${protocol}//${host}:${port}${endpoint}?client_id=${this.clientId}`;
    }
    
    /**
     * Connect to WebSocket server
     */
    connect() {
        if (this.ws && (this.ws.readyState === WebSocket.CONNECTING || this.ws.readyState === WebSocket.OPEN)) {
            console.log(`[WebSocket] Already connected or connecting to ${this.endpoint}`);
            return;
        }
        
        const url = this.getWebSocketUrl();
        console.log(`[WebSocket] Connecting to ${url}`);
        
        try {
            this.ws = new WebSocket(url);
            
            this.ws.onopen = this.handleOpen;
            this.ws.onmessage = this.handleMessage;
            this.ws.onerror = this.handleError;
            this.ws.onclose = this.handleClose;
            
        } catch (error) {
            console.error(`[WebSocket] Connection error:`, error);
            this.scheduleReconnect();
        }
    }
    
    /**
     * Handle WebSocket connection opened
     */
    handleOpen(event) {
        console.log(`[WebSocket] ✓ Connected to ${this.endpoint}`);
        this.isConnected = true;
        this.reconnectAttempts = 0;
        this.reconnectDelay = 1000; // Reset delay
        
        // Start heartbeat
        this.startHeartbeat();
        
        // Call user callback
        this.onConnect();
    }
    
    /**
     * Handle incoming WebSocket message
     */
    handleMessage(event) {
        try {
            const data = JSON.parse(event.data);
            
            // Handle pong responses (heartbeat)
            if (data.type === 'pong') {
                console.debug('[WebSocket] Heartbeat pong received');
                return;
            }
            
            // Handle connection acknowledgment
            if (data.type === 'connection_ack') {
                console.log(`[WebSocket] Connection acknowledged: ${data.client_id}`);
                return;
            }
            
            // Log received message
            console.log(`[WebSocket] Message received:`, data);
            
            // Call user message handler
            this.onMessage(data);
            
        } catch (error) {
            console.error('[WebSocket] Failed to parse message:', error, event.data);
        }
    }
    
    /**
     * Handle WebSocket error
     */
    handleError(error) {
        console.error(`[WebSocket] Error on ${this.endpoint}:`, error);
    }
    
    /**
     * Handle WebSocket connection closed
     */
    handleClose(event) {
        console.log(`[WebSocket] Connection closed: ${this.endpoint} (Code: ${event.code}, Reason: ${event.reason || 'Unknown'})`);
        this.isConnected = false;
        this.stopHeartbeat();
        
        // Call user callback
        this.onDisconnect();
        
        // Attempt reconnection if enabled
        if (this.shouldReconnect) {
            this.scheduleReconnect();
        }
    }
    
    /**
     * Schedule a reconnection attempt
     */
    scheduleReconnect() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.error(`[WebSocket] Max reconnection attempts (${this.maxReconnectAttempts}) reached. Giving up.`);
            return;
        }
        
        this.reconnectAttempts++;
        
        // Exponential backoff with jitter
        const jitter = Math.random() * 1000;
        const delay = Math.min(this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1) + jitter, this.maxReconnectDelay);
        
        console.log(`[WebSocket] Reconnecting in ${Math.round(delay / 1000)}s (Attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
        
        setTimeout(() => {
            console.log(`[WebSocket] Attempting reconnection ${this.reconnectAttempts}...`);
            this.connect();
        }, delay);
    }
    
    /**
     * Start heartbeat (ping) to keep connection alive
     */
    startHeartbeat() {
        this.stopHeartbeat(); // Clear any existing heartbeat
        
        this.heartbeatInterval = setInterval(() => {
            if (this.isConnected && this.ws.readyState === WebSocket.OPEN) {
                console.debug('[WebSocket] Sending heartbeat ping');
                this.send({ type: 'ping', timestamp: Date.now() });
            }
        }, this.heartbeatTimer);
    }
    
    /**
     * Stop heartbeat
     */
    stopHeartbeat() {
        if (this.heartbeatInterval) {
            clearInterval(this.heartbeatInterval);
            this.heartbeatInterval = null;
        }
    }
    
    /**
     * Send message to WebSocket server
     * @param {object} message - Message to send (will be JSON stringified)
     */
    send(message) {
        if (!this.isConnected || this.ws.readyState !== WebSocket.OPEN) {
            console.warn('[WebSocket] Cannot send message: not connected', message);
            return false;
        }
        
        try {
            this.ws.send(JSON.stringify(message));
            return true;
        } catch (error) {
            console.error('[WebSocket] Failed to send message:', error, message);
            return false;
        }
    }
    
    /**
     * Disconnect from WebSocket server
     * @param {boolean} permanent - If true, don't attempt reconnection
     */
    disconnect(permanent = false) {
        console.log(`[WebSocket] Disconnecting from ${this.endpoint} (permanent: ${permanent})`);
        
        if (permanent) {
            this.shouldReconnect = false;
        }
        
        this.stopHeartbeat();
        
        if (this.ws) {
            this.ws.close(1000, 'Client disconnect');
            this.ws = null;
        }
        
        this.isConnected = false;
    }
    
    /**
     * Check if WebSocket is connected
     * @returns {boolean} Connection status
     */
    isWebSocketConnected() {
        return this.isConnected && this.ws && this.ws.readyState === WebSocket.OPEN;
    }
    
    /**
     * Get current connection state
     * @returns {string} State: 'connected', 'connecting', 'disconnected', 'reconnecting'
     */
    getConnectionState() {
        if (this.isConnected && this.ws && this.ws.readyState === WebSocket.OPEN) {
            return 'connected';
        } else if (this.ws && this.ws.readyState === WebSocket.CONNECTING) {
            return 'connecting';
        } else if (this.reconnectAttempts > 0 && this.reconnectAttempts < this.maxReconnectAttempts) {
            return 'reconnecting';
        } else {
            return 'disconnected';
        }
    }
}

/**
 * WebSocket Manager
 * Manages multiple WebSocket connections for different purposes
 */
class WebSocketManager {
    constructor() {
        this.connections = {
            dashboard: null,
            anomalies: null,
            training: null,
            events: null
        };
    }
    
    /**
     * Connect to dashboard WebSocket
     * @param {function} onMessage - Message handler
     * @param {function} onConnect - Connection callback
     * @param {function} onDisconnect - Disconnection callback
     */
    connectDashboard(onMessage, onConnect = null, onDisconnect = null) {
        if (this.connections.dashboard) {
            console.log('[WebSocketManager] Dashboard already connected');
            return this.connections.dashboard;
        }
        
        this.connections.dashboard = new WebSocketClient(
            '/api/v1/ws/dashboard',
            onMessage,
            onConnect,
            onDisconnect
        );
        
        return this.connections.dashboard;
    }
    
    /**
     * Connect to anomalies WebSocket
     * @param {function} onMessage - Message handler
     * @param {function} onConnect - Connection callback
     * @param {function} onDisconnect - Disconnection callback
     */
    connectAnomalies(onMessage, onConnect = null, onDisconnect = null) {
        if (this.connections.anomalies) {
            console.log('[WebSocketManager] Anomalies already connected');
            return this.connections.anomalies;
        }
        
        this.connections.anomalies = new WebSocketClient(
            '/api/v1/ws/anomalies',
            onMessage,
            onConnect,
            onDisconnect
        );
        
        return this.connections.anomalies;
    }
    
    /**
     * Connect to training WebSocket
     * @param {function} onMessage - Message handler
     * @param {function} onConnect - Connection callback
     * @param {function} onDisconnect - Disconnection callback
     */
    connectTraining(onMessage, onConnect = null, onDisconnect = null) {
        if (this.connections.training) {
            console.log('[WebSocketManager] Training already connected');
            return this.connections.training;
        }
        
        this.connections.training = new WebSocketClient(
            '/api/v1/ws/training',
            onMessage,
            onConnect,
            onDisconnect
        );
        
        return this.connections.training;
    }
    
    /**
     * Connect to events WebSocket
     * @param {function} onMessage - Message handler
     * @param {function} onConnect - Connection callback
     * @param {function} onDisconnect - Disconnection callback
     */
    connectEvents(onMessage, onConnect = null, onDisconnect = null) {
        if (this.connections.events) {
            console.log('[WebSocketManager] Events already connected');
            return this.connections.events;
        }
        
        this.connections.events = new WebSocketClient(
            '/api/v1/ws/events',
            onMessage,
            onConnect,
            onDisconnect
        );
        
        return this.connections.events;
    }
    
    /**
     * Disconnect from specific WebSocket
     * @param {string} type - Connection type: 'dashboard', 'anomalies', 'training', 'events'
     * @param {boolean} permanent - If true, don't attempt reconnection
     */
    disconnect(type, permanent = false) {
        if (this.connections[type]) {
            this.connections[type].disconnect(permanent);
            if (permanent) {
                this.connections[type] = null;
            }
        }
    }
    
    /**
     * Disconnect from all WebSockets
     * @param {boolean} permanent - If true, don't attempt reconnection
     */
    disconnectAll(permanent = false) {
        Object.keys(this.connections).forEach(type => {
            this.disconnect(type, permanent);
        });
    }
    
    /**
     * Get connection status for all WebSockets
     * @returns {object} Status object with connection states
     */
    getStatus() {
        const status = {};
        Object.keys(this.connections).forEach(type => {
            if (this.connections[type]) {
                status[type] = this.connections[type].getConnectionState();
            } else {
                status[type] = 'not_initialized';
            }
        });
        return status;
    }
}

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { WebSocketClient, WebSocketManager };
}

// Make available globally
window.WebSocketClient = WebSocketClient;
window.WebSocketManager = WebSocketManager;

console.log('[WebSocket] Client utility loaded ✓');
