/**
 * LoadingSpinner - Reusable loading indicator component
 * 
 * @file loading-spinner.js
 * @description Displays animated loading spinners in various sizes and modes
 * @version 3.0.0
 * @date November 10, 2025
 * 
 * @example
 * // Inline spinner
 * const spinner = new LoadingSpinner('container-id', { size: 'md', mode: 'inline' });
 * spinner.show('Loading data...');
 * 
 * // Overlay spinner
 * const overlay = new LoadingSpinner('container-id', { mode: 'overlay' });
 * overlay.show();
 * overlay.hide();
 */

class LoadingSpinner extends BaseComponent {
  /**
   * Create a loading spinner
   * 
   * @param {string} containerId - DOM container ID
   * @param {object} options - Spinner configuration
   * @param {string} options.size - Spinner size: 'sm', 'md', 'lg' (default: 'md')
   * @param {string} options.mode - Display mode: 'inline', 'overlay' (default: 'inline')
   * @param {string} options.color - Spinner color: 'primary', 'white' (default: 'primary')
   * @param {string} options.message - Default message (default: 'Loading...')
   */
  constructor(containerId, options = {}) {
    super(containerId, { autoInit: false, ...options });
    
    this.size = options.size || 'md';
    this.mode = options.mode || 'inline';
    this.color = options.color || 'primary';
    this.defaultMessage = options.message || 'Loading...';
    
    this.isVisible = false;
  }
  
  /**
   * Show loading spinner
   * 
   * @param {string} message - Loading message
   */
  show(message = this.defaultMessage) {
    if (this.isVisible) return;
    
    this.isVisible = true;
    this.setState({ message }, false);
    this.render();
    this.emit('loading:start', { message });
  }
  
  /**
   * Hide loading spinner
   */
  hide() {
    if (!this.isVisible) return;
    
    this.isVisible = false;
    
    if (this.mode === 'overlay') {
      // Fade out animation
      const spinner = this.container.querySelector('.loading-spinner');
      if (spinner) {
        spinner.classList.add('fade-out');
        setTimeout(() => {
          this.container.innerHTML = '';
        }, 300);
      }
    } else {
      this.container.innerHTML = '';
    }
    
    this.emit('loading:complete');
  }
  
  /**
   * Update loading message
   * 
   * @param {string} message - New message
   */
  updateMessage(message) {
    const messageEl = this.container.querySelector('.loading-message');
    if (messageEl) {
      messageEl.textContent = message;
      this.emit('loading:message-updated', { message });
    }
  }
  
  /**
   * Render spinner
   */
  render() {
    if (!this.isVisible) {
      this.container.innerHTML = '';
      return;
    }
    
    const sizeClass = `spinner-${this.size}`;
    const modeClass = `mode-${this.mode}`;
    const colorClass = `color-${this.color}`;
    
    const html = `
      <div class="loading-spinner ${modeClass}">
        ${this.mode === 'overlay' ? '<div class="spinner-overlay"></div>' : ''}
        <div class="spinner-content">
          <div class="spinner ${sizeClass} ${colorClass}">
            <div class="spinner-circle"></div>
            <div class="spinner-circle"></div>
            <div class="spinner-circle"></div>
          </div>
          ${this.state.message ? `<p class="loading-message">${this.state.message}</p>` : ''}
        </div>
      </div>
    `;
    
    this.container.innerHTML = html;
  }
}

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
  module.exports = LoadingSpinner;
}
