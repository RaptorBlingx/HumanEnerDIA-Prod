/**
 * BaseComponent - Foundation for all UI components
 * 
 * @file base-component.js
 * @description Base class for all EnMS UI components. Provides event system,
 *              lifecycle management, and common utilities.
 * @version 3.0.0
 * @date November 10, 2025
 * 
 * @example
 * class MyComponent extends BaseComponent {
 *   async init() {
 *     const data = await this.fetchData();
 *     this.state = { data };
 *     this.render();
 *   }
 * 
 *   render() {
 *     this.container.innerHTML = `<div>${this.state.data}</div>`;
 *   }
 * }
 * 
 * const component = new MyComponent('container-id');
 */

class BaseComponent extends EventTarget {
  /**
   * Create a new component
   * 
   * @param {string} containerId - DOM container ID (without #)
   * @param {object} options - Component configuration
   * @param {boolean} options.autoInit - Auto-initialize on construction (default: true)
   * @param {boolean} options.debug - Enable debug logging (default: false)
   * @throws {Error} If container not found
   */
  constructor(containerId, options = {}) {
    super();
    
    this.containerId = containerId;
    this.container = document.getElementById(containerId);
    this.options = {
      autoInit: true,
      debug: false,
      ...options
    };
    
    if (!this.container) {
      throw new Error(`Container #${containerId} not found`);
    }
    
    // Component state
    this.state = {};
    this.isInitialized = false;
    this.isDestroyed = false;
    
    // Event listeners registry (for cleanup)
    this._eventListeners = [];
    this._intervals = [];
    this._timeouts = [];
    
    // Auto-initialize if enabled
    if (this.options.autoInit) {
      this.init().catch(error => {
        this.handleError(error);
      });
    }
  }
  
  /**
   * Initialize component (async setup, fetch data, etc.)
   * Override this method in subclasses
   * 
   * @async
   * @returns {Promise<void>}
   */
  async init() {
    if (this.isInitialized) {
      this.log('Already initialized');
      return;
    }
    
    this.log('Initializing...');
    this.isInitialized = true;
    this.emit('component:initialized', { component: this.constructor.name });
  }
  
  /**
   * Render component to DOM
   * Override this method in subclasses
   */
  render() {
    throw new Error('render() must be implemented by subclass');
  }
  
  /**
   * Update component state and re-render
   * 
   * @param {object} newState - Partial state updates
   * @param {boolean} shouldRender - Re-render after update (default: true)
   */
  setState(newState, shouldRender = true) {
    this.state = { ...this.state, ...newState };
    this.log('State updated:', newState);
    
    if (shouldRender) {
      this.render();
    }
    
    this.emit('component:updated', { state: this.state });
  }
  
  /**
   * Emit custom event
   * 
   * @param {string} eventName - Event name (namespace:action format)
   * @param {object} detail - Event payload
   * @param {boolean} bubbles - Event bubbles (default: true)
   */
  emit(eventName, detail = {}, bubbles = true) {
    const event = new CustomEvent(eventName, {
      detail: {
        ...detail,
        timestamp: new Date().toISOString(),
        component: this.constructor.name
      },
      bubbles,
      cancelable: true
    });
    
    this.dispatchEvent(event);
    
    // Also dispatch on container for DOM event delegation
    if (this.container) {
      this.container.dispatchEvent(event);
    }
    
    this.log(`Event: ${eventName}`, detail);
  }
  
  /**
   * Subscribe to events
   * Automatically tracks listeners for cleanup
   * 
   * @param {EventTarget} target - Event target (default: this)
   * @param {string} eventName - Event name
   * @param {function} handler - Event handler
   * @param {object} options - addEventListener options
   */
  on(eventName, handler, target = this, options = {}) {
    target.addEventListener(eventName, handler, options);
    
    // Track for cleanup
    this._eventListeners.push({ target, eventName, handler, options });
    
    this.log(`Subscribed to: ${eventName}`);
  }
  
  /**
   * Unsubscribe from events
   * 
   * @param {EventTarget} target - Event target
   * @param {string} eventName - Event name
   * @param {function} handler - Event handler
   */
  off(eventName, handler, target = this) {
    target.removeEventListener(eventName, handler);
    
    // Remove from tracking
    this._eventListeners = this._eventListeners.filter(
      listener => !(listener.target === target && 
                    listener.eventName === eventName && 
                    listener.handler === handler)
    );
    
    this.log(`Unsubscribed from: ${eventName}`);
  }
  
  /**
   * Set interval and track for cleanup
   * 
   * @param {function} callback - Interval callback
   * @param {number} delay - Delay in milliseconds
   * @returns {number} Interval ID
   */
  setInterval(callback, delay) {
    const id = setInterval(callback, delay);
    this._intervals.push(id);
    return id;
  }
  
  /**
   * Set timeout and track for cleanup
   * 
   * @param {function} callback - Timeout callback
   * @param {number} delay - Delay in milliseconds
   * @returns {number} Timeout ID
   */
  setTimeout(callback, delay) {
    const id = setTimeout(callback, delay);
    this._timeouts.push(id);
    return id;
  }
  
  /**
   * Show loading state
   * 
   * @param {string} message - Loading message (default: 'Loading...')
   */
  showLoading(message = 'Loading...') {
    this.container.innerHTML = `
      <div class="component-loading">
        <div class="spinner"></div>
        <p>${message}</p>
      </div>
    `;
    
    this.emit('loading:start', { message });
  }
  
  /**
   * Hide loading state
   */
  hideLoading() {
    const loading = this.container.querySelector('.component-loading');
    if (loading) {
      loading.remove();
    }
    
    this.emit('loading:complete');
  }
  
  /**
   * Show error message
   * 
   * @param {Error|string} error - Error object or message
   * @param {boolean} retryable - Show retry button
   */
  showError(error, retryable = false) {
    const message = error instanceof Error ? error.message : error;
    
    this.container.innerHTML = `
      <div class="component-error">
        <i class="icon-alert-circle"></i>
        <p>${message}</p>
        ${retryable ? '<button class="btn-retry" onclick="location.reload()">Retry</button>' : ''}
      </div>
    `;
    
    this.emit('error:show', { error: message, retryable });
  }
  
  /**
   * Handle errors
   * 
   * @param {Error} error - Error object
   */
  handleError(error) {
    console.error(`[${this.constructor.name}] Error:`, error);
    this.showError(error, true);
    this.emit('error:occurred', { error: error.message });
  }
  
  /**
   * Log debug messages
   * 
   * @param {...any} args - Arguments to log
   */
  log(...args) {
    if (this.options.debug) {
      console.log(`[${this.constructor.name}]`, ...args);
    }
  }
  
  /**
   * Clean up resources and destroy component
   * Call this when removing component from DOM
   */
  destroy() {
    if (this.isDestroyed) {
      this.log('Already destroyed');
      return;
    }
    
    this.log('Destroying...');
    
    // Remove all event listeners
    this._eventListeners.forEach(({ target, eventName, handler }) => {
      target.removeEventListener(eventName, handler);
    });
    this._eventListeners = [];
    
    // Clear all intervals
    this._intervals.forEach(id => clearInterval(id));
    this._intervals = [];
    
    // Clear all timeouts
    this._timeouts.forEach(id => clearTimeout(id));
    this._timeouts = [];
    
    // Clear container
    if (this.container) {
      this.container.innerHTML = '';
    }
    
    // Mark as destroyed
    this.isDestroyed = true;
    this.isInitialized = false;
    
    this.emit('component:destroyed', { component: this.constructor.name });
    
    this.log('Destroyed');
  }
}

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
  module.exports = BaseComponent;
}
