/**
 * SEUSelector - SEU dropdown selector with search
 * 
 * @file seu-selector.js
 * @description Dropdown selector for Significant Energy Uses with search/filter
 * @version 3.0.0
 * @date November 10, 2025
 * 
 * @fires seu:selected - When SEU is selected
 * @fires seu:loading - When loading SEUs
 * @fires seu:error - When error occurs
 * 
 * @example
 * const selector = new SEUSelector('seu-selector');
 * selector.on('seu:selected', (e) => {
 *   console.log('Selected:', e.detail.seuName, e.detail.energySources);
 * });
 */

class SEUSelector extends BaseComponent {
  /**
   * Create SEU selector
   * 
   * @param {string} containerId - DOM container ID
   * @param {object} options - Component options
   * @param {boolean} options.multiSelect - Enable multi-select mode (default: false)
   * @param {string} options.placeholder - Placeholder text
   * @param {boolean} options.showCount - Show SEU count (default: true)
   */
  constructor(containerId, options = {}) {
    super(containerId, { autoInit: true, ...options });
    
    this.multiSelect = options.multiSelect || false;
    this.placeholder = options.placeholder || '-- Select a Significant Energy Use --';
    this.showCount = options.showCount !== false;
    
    this.seus = [];
    this.selectedSEUs = [];
  }
  
  /**
   * Initialize - fetch SEUs from API
   */
  async init() {
    await super.init();
    
    this.showLoading('Loading SEUs...');
    this.emit('seu:loading', { isLoading: true });
    
    try {
      // Try cache first
      const cached = StateManager.get('api_cache_seus');
      if (cached) {
        this.seus = cached;
      } else {
        // Fetch from API (using global apiClient if available)
        if (typeof apiClient !== 'undefined') {
          this.seus = await apiClient.getSEUs();
        } else {
          // Fallback to direct fetch
          const response = await fetch('/api/v1/seus');
          if (!response.ok) throw new Error('Failed to fetch SEUs');
          this.seus = await response.json();
        }
        
        // Cache for 5 minutes
        StateManager.set('api_cache_seus', this.seus, 300);
      }
      
      this.hideLoading();
      this.render();
      
      // Restore previous selection
      const savedSelection = StateManager.get('seu_selection');
      if (savedSelection) {
        this.selectSEU(savedSelection.seuName);
      }
      
      this.emit('seu:loading', { isLoading: false });
    } catch (error) {
      this.hideLoading();
      this.showError(error);
      this.emit('seu:error', { error: error.message });
    }
  }
  
  /**
   * Render SEU selector
   */
  render() {
    if (this.multiSelect) {
      this.renderMultiSelect();
    } else {
      this.renderSingleSelect();
    }
  }
  
  /**
   * Render single-select dropdown
   */
  renderSingleSelect() {
    const html = `
      <div class="seu-selector">
        <label for="seu-dropdown">Select SEU:</label>
        <select id="seu-dropdown" class="form-control">
          <option value="">${this.placeholder}</option>
          ${this.seus.map(seu => `
            <option value="${seu.seu_name}" 
                    data-id="${seu.id}"
                    data-energy-sources='${JSON.stringify(seu.energy_sources || [])}'>
              ${seu.seu_name} (${seu.machine_type || 'unknown'})
            </option>
          `).join('')}
        </select>
        ${this.showCount ? `<small class="text-muted">${this.seus.length} SEUs available</small>` : ''}
      </div>
    `;
    
    this.container.innerHTML = html;
    
    // Attach event listener
    const dropdown = this.container.querySelector('#seu-dropdown');
    dropdown.addEventListener('change', (e) => this.handleSingleSelection(e));
  }
  
  /**
   * Render multi-select checkboxes
   */
  renderMultiSelect() {
    const html = `
      <div class="seu-selector multi-select">
        <label>Select SEUs:</label>
        <div class="seu-list">
          ${this.seus.map(seu => `
            <div class="seu-option">
              <input type="checkbox" 
                     id="seu-${seu.id}" 
                     value="${seu.seu_name}"
                     data-id="${seu.id}"
                     data-energy-sources='${JSON.stringify(seu.energy_sources || [])}'>
              <label for="seu-${seu.id}">
                ${seu.seu_name} <small>(${seu.machine_type || 'unknown'})</small>
              </label>
            </div>
          `).join('')}
        </div>
        ${this.showCount ? `<small class="text-muted">${this.selectedSEUs.length} of ${this.seus.length} selected</small>` : ''}
      </div>
    `;
    
    this.container.innerHTML = html;
    
    // Attach event listeners
    const checkboxes = this.container.querySelectorAll('input[type="checkbox"]');
    checkboxes.forEach(checkbox => {
      checkbox.addEventListener('change', () => this.handleMultiSelection());
    });
  }
  
  /**
   * Handle single SEU selection
   */
  handleSingleSelection(event) {
    const selectedOption = event.target.selectedOptions[0];
    if (!selectedOption.value) return;
    
    const seuName = selectedOption.value;
    const seuId = selectedOption.dataset.id;
    const energySources = JSON.parse(selectedOption.dataset.energySources);
    const machineType = this.seus.find(s => s.seu_name === seuName)?.machine_type;
    
    this.selectedSEUs = [{ seuName, seuId, energySources, machineType }];
    
    // Persist selection
    StateManager.set('seu_selection', this.selectedSEUs[0], 3600);
    
    // Emit event
    this.emit('seu:selected', {
      seuName,
      seuId,
      energySources,
      machineType
    });
  }
  
  /**
   * Handle multi-SEU selection
   */
  handleMultiSelection() {
    const checkboxes = this.container.querySelectorAll('input[type="checkbox"]:checked');
    
    this.selectedSEUs = Array.from(checkboxes).map(checkbox => ({
      seuName: checkbox.value,
      seuId: checkbox.dataset.id,
      energySources: JSON.parse(checkbox.dataset.energySources)
    }));
    
    // Update count
    const countEl = this.container.querySelector('.text-muted');
    if (countEl) {
      countEl.textContent = `${this.selectedSEUs.length} of ${this.seus.length} selected`;
    }
    
    // Emit event
    this.emit('seu:selected', {
      seuNames: this.selectedSEUs.map(s => s.seuName),
      seus: this.selectedSEUs
    });
  }
  
  /**
   * Programmatically select SEU
   * 
   * @param {string} seuName - SEU name to select
   */
  selectSEU(seuName) {
    if (this.multiSelect) {
      const checkbox = this.container.querySelector(`input[value="${seuName}"]`);
      if (checkbox) {
        checkbox.checked = true;
        this.handleMultiSelection();
      }
    } else {
      const dropdown = this.container.querySelector('#seu-dropdown');
      if (dropdown) {
        dropdown.value = seuName;
        dropdown.dispatchEvent(new Event('change'));
      }
    }
  }
  
  /**
   * Get currently selected SEU(s)
   * 
   * @returns {array} Selected SEUs
   */
  getSelected() {
    return this.selectedSEUs;
  }
  
  /**
   * Clear selection
   */
  clearSelection() {
    if (this.multiSelect) {
      const checkboxes = this.container.querySelectorAll('input[type="checkbox"]');
      checkboxes.forEach(cb => cb.checked = false);
    } else {
      const dropdown = this.container.querySelector('#seu-dropdown');
      if (dropdown) dropdown.value = '';
    }
    
    this.selectedSEUs = [];
    StateManager.remove('seu_selection');
  }
}

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
  module.exports = SEUSelector;
}
