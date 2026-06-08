/**
 * ChartContainer Component
 * 
 * @file chart-container.js
 * @description Responsive wrapper for Chart.js instances with loading, error states, and export
 * @version 3.0.0
 * @date November 10, 2025
 */

import BaseComponent from './base-component.js';

/**
 * @class ChartContainer
 * @extends BaseComponent
 * @description Manages Chart.js lifecycle with export, fullscreen, and responsive behavior
 * 
 * Features:
 * - Responsive canvas sizing with debounced resize
 * - Loading and error state UI
 * - Export to PNG and CSV
 * - Fullscreen mode
 * - Auto-cleanup of Chart.js instances
 * 
 * @example
 * const container = new ChartContainer('my-chart');
 * await container.init();
 * 
 * const data = { labels: [...], datasets: [...] };
 * const config = { type: 'line', data, options: {...} };
 * container.renderChart(config);
 * 
 * container.on('chart:export', ({ format, filename }) => {
 *   console.log(`Exported ${filename} as ${format}`);
 * });
 */
export default class ChartContainer extends BaseComponent {
  /**
   * @param {string} containerId - Container element ID
   * @param {Object} options - Configuration options
   * @param {string} options.title - Chart title
   * @param {boolean} options.showExport - Show export buttons (default: true)
   * @param {boolean} options.showFullscreen - Show fullscreen button (default: true)
   * @param {number} options.minHeight - Minimum canvas height in px (default: 300)
   * @param {Object} options.exportOptions - CSV export configuration
   */
  constructor(containerId, options = {}) {
    super(containerId);
    
    this.title = options.title || 'Chart';
    this.showExport = options.showExport !== false;
    this.showFullscreen = options.showFullscreen !== false;
    this.minHeight = options.minHeight || 300;
    this.exportOptions = options.exportOptions || {};
    
    this.chart = null;
    this.chartData = null;
    this.chartConfig = null;
    this.resizeObserver = null;
  }

  /**
   * Initialize container and setup resize handling
   */
  async init() {
    await super.init();
    
    this.render();
    this.setupResizeObserver();
    
    return this;
  }

  /**
   * Render container structure
   */
  render() {
    this.container.innerHTML = `
      <div class="chart-container">
        <div class="chart-header">
          <h3 class="chart-title">${this.title}</h3>
          ${this.renderActions()}
        </div>
        <div class="chart-canvas">
          <canvas id="${this.containerId}-canvas"></canvas>
        </div>
      </div>
    `;
    
    this.attachEventListeners();
  }

  /**
   * Render action buttons
   */
  renderActions() {
    if (!this.showExport && !this.showFullscreen) {
      return '';
    }
    
    const exportButtons = this.showExport ? `
      <button class="chart-btn btn-export-png" title="Export as PNG">
        📊 PNG
      </button>
      <button class="chart-btn btn-export-csv" title="Export as CSV">
        📁 CSV
      </button>
    ` : '';
    
    const fullscreenButton = this.showFullscreen ? `
      <button class="chart-btn btn-fullscreen" title="Fullscreen">
        ⛶ Fullscreen
      </button>
    ` : '';
    
    return `
      <div class="chart-actions">
        ${exportButtons}
        ${fullscreenButton}
      </div>
    `;
  }

  /**
   * Attach event listeners to action buttons
   */
  attachEventListeners() {
    const pngBtn = this.container.querySelector('.btn-export-png');
    const csvBtn = this.container.querySelector('.btn-export-csv');
    const fullscreenBtn = this.container.querySelector('.btn-fullscreen');
    
    if (pngBtn) {
      pngBtn.addEventListener('click', () => this.exportPNG());
    }
    
    if (csvBtn) {
      csvBtn.addEventListener('click', () => this.exportCSV());
    }
    
    if (fullscreenBtn) {
      fullscreenBtn.addEventListener('click', () => this.toggleFullscreen());
    }
  }

  /**
   * Render Chart.js instance
   * @param {Object} config - Chart.js configuration object
   * @param {string} config.type - Chart type (line, bar, pie, etc.)
   * @param {Object} config.data - Chart data
   * @param {Object} config.options - Chart options
   */
  renderChart(config) {
    // Destroy existing chart
    if (this.chart) {
      this.chart.destroy();
      this.chart = null;
    }
    
    // Store config for re-renders
    this.chartConfig = config;
    this.chartData = config.data;
    
    // Get canvas context
    const canvas = this.container.querySelector(`#${this.containerId}-canvas`);
    if (!canvas) {
      this.showError('Canvas element not found');
      return;
    }
    
    const ctx = canvas.getContext('2d');
    
    try {
      // Create Chart.js instance
      this.chart = new Chart(ctx, {
        ...config,
        options: {
          ...config.options,
          responsive: true,
          maintainAspectRatio: false,
          ...this.getResponsiveOptions()
        }
      });
      
      this.hideLoading();
      this.emit('chart:rendered', { config });
    } catch (error) {
      console.error('[ChartContainer] Chart render error:', error);
      this.showError('Failed to render chart');
      this.emit('chart:error', { error: error.message });
    }
  }

  /**
   * Get responsive Chart.js options
   */
  getResponsiveOptions() {
    return {
      plugins: {
        legend: {
          display: true,
          position: window.innerWidth < 768 ? 'bottom' : 'top'
        }
      },
      scales: {
        x: {
          ticks: {
            maxRotation: window.innerWidth < 768 ? 45 : 0
          }
        }
      }
    };
  }

  /**
   * Update chart data without full re-render
   * @param {Object} newData - New chart data
   */
  updateData(newData) {
    if (!this.chart) {
      console.warn('[ChartContainer] No chart to update');
      return;
    }
    
    this.chartData = newData;
    this.chart.data = newData;
    this.chart.update();
    
    this.emit('chart:updated', { data: newData });
  }

  /**
   * Export chart as PNG image
   */
  exportPNG() {
    if (!this.chart) {
      this.showError('No chart to export');
      return;
    }
    
    try {
      const canvas = this.chart.canvas;
      const url = canvas.toDataURL('image/png');
      
      const filename = this.generateFilename('png');
      const link = document.createElement('a');
      link.download = filename;
      link.href = url;
      link.click();
      
      this.emit('chart:export', { format: 'png', filename });
    } catch (error) {
      console.error('[ChartContainer] PNG export error:', error);
      this.showError('Failed to export PNG');
    }
  }

  /**
   * Export chart data as CSV
   */
  exportCSV() {
    if (!this.chartData) {
      this.showError('No data to export');
      return;
    }
    
    try {
      const csv = this.convertToCSV(this.chartData);
      const blob = new Blob([csv], { type: 'text/csv' });
      const url = URL.createObjectURL(blob);
      
      const filename = this.generateFilename('csv');
      const link = document.createElement('a');
      link.download = filename;
      link.href = url;
      link.click();
      
      URL.revokeObjectURL(url);
      
      this.emit('chart:export', { format: 'csv', filename });
    } catch (error) {
      console.error('[ChartContainer] CSV export error:', error);
      this.showError('Failed to export CSV');
    }
  }

  /**
   * Convert Chart.js data to CSV format
   * @param {Object} data - Chart data object
   * @returns {string} CSV string
   */
  convertToCSV(data) {
    const rows = [];
    
    // Header row
    const headers = ['Label', ...data.datasets.map(ds => ds.label || 'Data')];
    rows.push(headers.join(','));
    
    // Data rows
    const labelCount = data.labels.length;
    for (let i = 0; i < labelCount; i++) {
      const row = [data.labels[i]];
      
      for (const dataset of data.datasets) {
        const value = dataset.data[i];
        row.push(value !== null && value !== undefined ? value : '');
      }
      
      rows.push(row.join(','));
    }
    
    return rows.join('\n');
  }

  /**
   * Generate export filename with timestamp
   * @param {string} extension - File extension (png or csv)
   * @returns {string} Filename
   */
  generateFilename(extension) {
    const timestamp = new Date().toISOString().slice(0, 19).replace(/:/g, '-');
    const sanitizedTitle = this.title.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '');
    return `${sanitizedTitle}-${timestamp}.${extension}`;
  }

  /**
   * Toggle fullscreen mode
   */
  toggleFullscreen() {
    const chartContainer = this.container.querySelector('.chart-container');
    
    if (!document.fullscreenElement) {
      chartContainer.requestFullscreen().catch(err => {
        console.error('[ChartContainer] Fullscreen error:', err);
        this.showError('Fullscreen not supported');
      });
    } else {
      document.exitFullscreen();
    }
  }

  /**
   * Setup ResizeObserver for responsive charts
   */
  setupResizeObserver() {
    if (!window.ResizeObserver) {
      // Fallback to window resize with debounce
      let resizeTimeout;
      window.addEventListener('resize', () => {
        clearTimeout(resizeTimeout);
        resizeTimeout = setTimeout(() => this.handleResize(), 200);
      });
      return;
    }
    
    this.resizeObserver = new ResizeObserver(() => {
      this.handleResize();
    });
    
    this.resizeObserver.observe(this.container);
  }

  /**
   * Handle container resize
   */
  handleResize() {
    if (this.chart) {
      this.chart.options = {
        ...this.chart.options,
        ...this.getResponsiveOptions()
      };
      this.chart.resize();
      this.emit('chart:resized', { width: this.container.offsetWidth });
    }
  }

  /**
   * Show "no data" message
   * @param {string} message - Custom message (optional)
   */
  showNoData(message = 'No data available') {
    const canvasContainer = this.container.querySelector('.chart-canvas');
    canvasContainer.innerHTML = `
      <div class="chart-no-data">
        <i class="icon-chart-empty">📊</i>
        <p>${message}</p>
      </div>
    `;
  }

  /**
   * Cleanup resources
   */
  destroy() {
    // Destroy Chart.js instance
    if (this.chart) {
      this.chart.destroy();
      this.chart = null;
    }
    
    // Disconnect ResizeObserver
    if (this.resizeObserver) {
      this.resizeObserver.disconnect();
      this.resizeObserver = null;
    }
    
    super.destroy();
  }
}
