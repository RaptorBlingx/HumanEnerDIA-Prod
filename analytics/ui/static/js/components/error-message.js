/**
 * ErrorMessage - Reusable error message component
 * 
 * @file error-message.js
 * @description Displays contextual error/success/warning messages
 * @version 3.0.0
 * @date November 10, 2025
 * 
 * @example
 * // Show error with retry
 * const errorMsg = new ErrorMessage('container-id');
 * errorMsg.show('Failed to load data', 'error', true, () => location.reload());
 * 
 * // Show success with auto-hide
 * errorMsg.show('Saved successfully!', 'success');
 * 
 * // Show warning
 * errorMsg.show('This action cannot be undone', 'warning');
 */

class ErrorMessage extends BaseComponent {
  /**
   * Create an error message component
   * 
   * @param {string} containerId - DOM container ID
   * @param {object} options - Component configuration
   * @param {number} options.autoHideDelay - Auto-hide delay in ms (default: 0 = no auto-hide)
   * @param {boolean} options.dismissible - Show close button (default: true)
   */
  constructor(containerId, options = {}) {
    super(containerId, { autoInit: false, ...options });
    
    this.autoHideDelay = options.autoHideDelay || 0;
    this.dismissible = options.dismissible !== false;
    this.autoHideTimeout = null;
  }
  
  /**
   * Show message
   * 
   * @param {string} message - Message text
   * @param {string} type - Message type: 'error', 'warning', 'info', 'success'
   * @param {boolean} retryable - Show retry button
   * @param {function} onRetry - Retry callback
   * @param {number} autoHide - Auto-hide delay in ms (overrides default)
   */
  show(message, type = 'info', retryable = false, onRetry = null, autoHide = null) {
    this.setState({
      message,
      type,
      retryable,
      onRetry
    }, false);
    
    this.render();
    
    // Auto-hide if configured
    const delay = autoHide !== null ? autoHide : this.autoHideDelay;
    if (delay > 0 && type === 'success') {
      this.autoHideTimeout = this.setTimeout(() => {
        this.hide();
      }, delay);
    }
    
    this.emit('error:show', { message, type, retryable });
  }
  
  /**
   * Hide message
   */
  hide() {
    // Clear auto-hide timeout
    if (this.autoHideTimeout) {
      clearTimeout(this.autoHideTimeout);
      this.autoHideTimeout = null;
    }
    
    // Fade out animation
    const messageEl = this.container.querySelector('.error-message');
    if (messageEl) {
      messageEl.classList.add('fade-out');
      setTimeout(() => {
        this.container.innerHTML = '';
      }, 300);
    }
    
    this.emit('error:dismiss');
  }
  
  /**
   * Render error message
   */
  render() {
    const { message, type, retryable, onRetry } = this.state;
    
    if (!message) {
      this.container.innerHTML = '';
      return;
    }
    
    // Icon mapping
    const icons = {
      error: 'icon-alert-circle',
      warning: 'icon-alert-triangle',
      info: 'icon-info',
      success: 'icon-check-circle'
    };
    
    const icon = icons[type] || icons.info;
    
    const html = `
      <div class="error-message type-${type}">
        <div class="error-icon">
          <i class="${icon}"></i>
        </div>
        <div class="error-content">
          <p class="error-text">${message}</p>
          <div class="error-actions">
            ${retryable && onRetry ? '<button class="btn-retry" id="error-retry-btn">Retry</button>' : ''}
            ${this.dismissible ? '<button class="btn-dismiss" id="error-dismiss-btn">×</button>' : ''}
          </div>
        </div>
      </div>
    `;
    
    this.container.innerHTML = html;
    
    // Attach event listeners
    if (retryable && onRetry) {
      const retryBtn = this.container.querySelector('#error-retry-btn');
      if (retryBtn) {
        retryBtn.addEventListener('click', () => {
          this.emit('error:retry');
          onRetry();
        });
      }
    }
    
    if (this.dismissible) {
      const dismissBtn = this.container.querySelector('#error-dismiss-btn');
      if (dismissBtn) {
        dismissBtn.addEventListener('click', () => this.hide());
      }
    }
  }
  
  /**
   * Shortcut: Show error message
   * 
   * @param {string} message - Error message
   * @param {boolean} retryable - Show retry button
   * @param {function} onRetry - Retry callback
   */
  showError(message, retryable = false, onRetry = null) {
    this.show(message, 'error', retryable, onRetry);
  }
  
  /**
   * Shortcut: Show warning message
   * 
   * @param {string} message - Warning message
   */
  showWarning(message) {
    this.show(message, 'warning');
  }
  
  /**
   * Shortcut: Show info message
   * 
   * @param {string} message - Info message
   */
  showInfo(message) {
    this.show(message, 'info');
  }
  
  /**
   * Shortcut: Show success message (auto-hides after 5s)
   * 
   * @param {string} message - Success message
   * @param {number} autoHide - Auto-hide delay in ms (default: 5000)
   */
  showSuccess(message, autoHide = 5000) {
    this.show(message, 'success', false, null, autoHide);
  }
}

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
  module.exports = ErrorMessage;
}
