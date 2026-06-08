/**
 * EnergySourceFilter - Multi-select filter for energy sources
 * 
 * @file energy-source-filter.js
 * @description Filter component for selecting energy sources with auto-select logic
 * @version 3.0.0
 * @date November 10, 2025
 * 
 * @fires energy:filtered - When energy sources are selected
 * 
 * @example
 * const filter = new EnergySourceFilter('energy-filter');
 * filter.on('energy:filtered', (e) => {
 *   console.log('Selected sources:', e.detail.sources);
 * });
 * 
 * // Listen for SEU selection to auto-configure
 * document.addEventListener('seu:selected', (e) => {
 *   filter.handleSEUSelected(e.detail);
 * });
 */

class EnergySourceFilter extends BaseComponent {
  /**
   * Create energy source filter
   * 
   * @param {string} containerId - DOM container ID
   * @param {object} options - Component options
   * @param {string} options.mode - Selection mode: 'single', 'multi' (default: 'single')
   */
  constructor(containerId, options = {}) {
    super(containerId, { autoInit: true, ...options });
    
    this.mode = options.mode || 'single';
    this.availableSources = [];
    this.selectedSources = [];
    this.seuName = null;
  }
  
  /**
   * Initialize filter
   */
  async init() {
    await super.init();
    
    this.render();
    
    // Listen for SEU selection
    document.addEventListener('seu:selected', (e) => {
      this.handleSEUSelected(e.detail);
    });
    
    // Restore previous selection
    const savedFilter = StateManager.get('energy_filter');
    if (savedFilter) {
      this.availableSources = savedFilter.sources || [];
      this.selectedSources = savedFilter.sources || [];
      this.render();
    }
  }
  
  /**
   * Handle SEU selection
   * 
   * @param {object} detail - SEU selection details
   */
  handleSEUSelected({ seuName, energySources = [] }) {
    this.availableSources = energySources;
    this.seuName = seuName;
    
    // Auto-select if single energy source
    if (energySources.length === 1) {
      this.selectedSources = [energySources[0]];
      this.mode = 'single';
    } else if (energySources.length > 1) {
      this.selectedSources = []; // User must select
      this.mode = 'radio'; // One source at a time for multi-energy SEU
    } else {
      this.selectedSources = [];
      this.availableSources = [];
    }
    
    this.render();
    
    // Auto-emit if single energy (form ready immediately)
    if (energySources.length === 1) {
      this.emitChange();
    }
  }
  
  /**
   * Render energy source filter
   */
  render() {
    const allSources = [
      { value: 'electricity', label: 'Electricity', color: '#3b82f6', icon: '⚡' },
      { value: 'natural_gas', label: 'Natural Gas', color: '#f59e0b', icon: '🔥' },
      { value: 'steam', label: 'Steam', color: '#ef4444', icon: '♨️' },
      { value: 'compressed_air', label: 'Compressed Air', color: '#10b981', icon: '💨' }
    ];
    
    const isSingleEnergy = this.availableSources.length === 1;
    const inputType = (this.mode === 'multi' || this.mode === 'checkbox') ? 'checkbox' : 'radio';
    
    const html = `
      <div class="energy-filter">
        <label>Energy Source:</label>
        <div class="energy-options">
          ${allSources.map(source => {
            const isAvailable = this.availableSources.includes(source.value);
            const isSelected = this.selectedSources.includes(source.value);
            const isDisabled = !isAvailable || isSingleEnergy;
            
            return `
              <div class="energy-option ${isDisabled ? 'disabled' : ''} ${isSelected ? 'selected' : ''}" 
                   style="border-left: 4px solid ${isAvailable ? source.color : '#ccc'}">
                <input 
                  type="${inputType}" 
                  id="energy-${source.value}" 
                  name="energy-source"
                  value="${source.value}"
                  ${isSelected ? 'checked' : ''}
                  ${isDisabled ? 'disabled' : ''}
                  data-color="${source.color}">
                <label for="energy-${source.value}">
                  <span class="energy-icon">${source.icon}</span>
                  <span class="energy-label">${source.label}</span>
                  ${!isAvailable ? '<small class="badge-unavailable">unavailable</small>' : ''}
                  ${isSingleEnergy && isSelected ? '<small class="badge-auto">auto-selected</small>' : ''}
                </label>
              </div>
            `;
          }).join('')}
        </div>
        ${isSingleEnergy 
          ? '<small class="text-muted">✓ Single energy source (auto-selected)</small>' 
          : this.availableSources.length > 1
            ? '<small class="text-muted">Select one energy source to analyze</small>'
            : '<small class="text-muted">Select an SEU to enable energy source filter</small>'
        }
      </div>
    `;
    
    this.container.innerHTML = html;
    
    // Attach event listeners
    const inputs = this.container.querySelectorAll('input[type="radio"], input[type="checkbox"]');
    inputs.forEach(input => {
      input.addEventListener('change', (e) => this.handleChange(e));
    });
  }
  
  /**
   * Handle energy source selection
   */
  handleChange(event) {
    const value = event.target.value;
    
    if (this.mode === 'multi' || this.mode === 'checkbox') {
      // Checkbox mode - multiple selection
      if (event.target.checked) {
        if (!this.selectedSources.includes(value)) {
          this.selectedSources.push(value);
        }
      } else {
        this.selectedSources = this.selectedSources.filter(s => s !== value);
      }
    } else {
      // Radio mode - single selection
      this.selectedSources = [value];
    }
    
    // Update visual state
    this.updateVisualState();
    
    // Emit change event
    this.emitChange();
  }
  
  /**
   * Update visual state of options
   */
  updateVisualState() {
    const options = this.container.querySelectorAll('.energy-option');
    options.forEach(option => {
      const input = option.querySelector('input');
      if (input.checked) {
        option.classList.add('selected');
      } else {
        option.classList.remove('selected');
      }
    });
  }
  
  /**
   * Emit energy:filtered event
   */
  emitChange() {
    this.emit('energy:filtered', {
      sources: this.selectedSources,
      seuName: this.seuName
    });
    
    // Persist selection
    StateManager.set('energy_filter', {
      sources: this.selectedSources,
      seuName: this.seuName
    }, 3600); // 1 hour TTL
  }
  
  /**
   * Get selected energy sources
   * 
   * @returns {array} Selected energy sources
   */
  getSelected() {
    return this.selectedSources;
  }
  
  /**
   * Set mode (single vs multi)
   * 
   * @param {string} mode - 'single', 'radio', 'multi', or 'checkbox'
   */
  setMode(mode) {
    this.mode = mode;
    this.render();
  }
  
  /**
   * Clear selection
   */
  clearSelection() {
    this.selectedSources = [];
    this.availableSources = [];
    this.seuName = null;
    StateManager.remove('energy_filter');
    this.render();
  }
}

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
  module.exports = EnergySourceFilter;
}
