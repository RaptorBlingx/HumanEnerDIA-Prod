/**
 * API Client for EnMS v3
 * 
 * @file api-client.js
 * @description Centralized API client with caching, retry logic, and error handling
 * @version 3.0.0
 * @date November 10, 2025
 */

/**
 * @class APIClient
 * @description HTTP client for EnMS v3 API with retry, caching, and standardized error handling
 * 
 * Features:
 * - Automatic retry with exponential backoff
 * - Response caching with TTL
 * - Standardized error format
 * - Request/response logging
 * - AbortController support for cancellation
 * 
 * @example
 * const client = new APIClient('/api/v1');
 * 
 * // Cached request
 * const seus = await client.getSEUs({ cache: true });
 * 
 * // Non-cached request
 * const anomalies = await client.getAnomalies('last-24h', { cache: false });
 */
export default class APIClient {
  /**
   * @param {string} baseURL - Base API URL (default: '/api/v1')
   * @param {Object} options - Configuration options
   * @param {number} options.timeout - Request timeout in ms (default: 30000)
   * @param {number} options.maxRetries - Max retry attempts (default: 3)
   * @param {Array<number>} options.retryDelays - Retry delays in ms (default: [2000, 4000, 8000])
   * @param {boolean} options.enableLogging - Enable console logging (default: false)
   */
  constructor(baseURL = '/api/v1', options = {}) {
    this.baseURL = baseURL;
    this.timeout = options.timeout || 30000;
    this.maxRetries = options.maxRetries || 3;
    this.retryDelays = options.retryDelays || [2000, 4000, 8000];
    this.enableLogging = options.enableLogging || false;
    
    this.cache = new Map();
    this.abortControllers = new Map();
  }

  /**
   * Generic HTTP request method
   * @param {string} endpoint - API endpoint (without base URL)
   * @param {Object} options - Fetch options
   * @param {Object} requestOptions - Client-specific options
   * @param {boolean} requestOptions.cache - Enable caching (default: false)
   * @param {number} requestOptions.cacheTTL - Cache TTL in ms (default: 300000 = 5min)
   * @param {number} requestOptions.retries - Override max retries
   * @returns {Promise<Object>} Response data
   */
  async request(endpoint, options = {}, requestOptions = {}) {
    const url = `${this.baseURL}${endpoint}`;
    const cacheKey = `${options.method || 'GET'}:${url}`;
    const enableCache = requestOptions.cache || false;
    const cacheTTL = requestOptions.cacheTTL || 300000; // 5 min default
    const maxRetries = requestOptions.retries !== undefined ? requestOptions.retries : this.maxRetries;
    
    // Check cache
    if (enableCache && this.cache.has(cacheKey)) {
      const cached = this.cache.get(cacheKey);
      if (Date.now() < cached.expires) {
        this.log('Cache hit:', cacheKey);
        return cached.data;
      } else {
        this.cache.delete(cacheKey);
      }
    }
    
    // Create AbortController for timeout
    const controller = new AbortController();
    const requestId = `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    this.abortControllers.set(requestId, controller);
    
    const timeoutId = setTimeout(() => controller.abort(), this.timeout);
    
    let lastError = null;
    
    // Retry loop
    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      try {
        this.log(`Request [attempt ${attempt + 1}/${maxRetries + 1}]:`, url);
        
        const response = await fetch(url, {
          ...options,
          signal: controller.signal,
          headers: {
            'Content-Type': 'application/json',
            ...options.headers
          }
        });
        
        clearTimeout(timeoutId);
        this.abortControllers.delete(requestId);
        
        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          throw new APIError(
            errorData.message || `HTTP ${response.status}: ${response.statusText}`,
            response.status,
            this.isRetryableStatus(response.status)
          );
        }
        
        const data = await response.json();
        
        // Cache successful response
        if (enableCache) {
          this.cache.set(cacheKey, {
            data,
            expires: Date.now() + cacheTTL
          });
        }
        
        this.log('Response:', data);
        return data;
        
      } catch (error) {
        lastError = error;
        
        // Don't retry on abort or non-retryable errors
        if (error.name === 'AbortError') {
          throw new APIError('Request timeout', 408, true);
        }
        
        if (error instanceof APIError && !error.retryable) {
          throw error;
        }
        
        // Wait before retry
        if (attempt < maxRetries) {
          const delay = this.retryDelays[attempt] || this.retryDelays[this.retryDelays.length - 1];
          this.log(`Retrying in ${delay}ms...`);
          await this.sleep(delay);
        }
      }
    }
    
    // All retries failed
    clearTimeout(timeoutId);
    this.abortControllers.delete(requestId);
    throw lastError;
  }

  /**
   * Determine if HTTP status is retryable
   * @param {number} status - HTTP status code
   * @returns {boolean} True if retryable
   */
  isRetryableStatus(status) {
    return status === 408 || status === 429 || status >= 500;
  }

  /**
   * GET request helper
   */
  async get(endpoint, params = {}, options = {}) {
    const queryString = new URLSearchParams(params).toString();
    const url = queryString ? `${endpoint}?${queryString}` : endpoint;
    return this.request(url, { method: 'GET' }, options);
  }

  /**
   * POST request helper
   */
  async post(endpoint, body = {}, options = {}) {
    return this.request(endpoint, {
      method: 'POST',
      body: JSON.stringify(body)
    }, options);
  }

  /**
   * PUT request helper
   */
  async put(endpoint, body = {}, options = {}) {
    return this.request(endpoint, {
      method: 'PUT',
      body: JSON.stringify(body)
    }, options);
  }

  /**
   * DELETE request helper
   */
  async delete(endpoint, options = {}) {
    return this.request(endpoint, { method: 'DELETE' }, options);
  }

  /* ============================================================================
     V3 API METHODS
     ========================================================================= */

  /**
   * Get all SEUs (Significant Energy Uses)
   * @param {Object} options - Request options
   * @returns {Promise<Array>} Array of SEU objects
   */
  async getSEUs(options = {}) {
    return this.get('/seus', {}, { cache: true, cacheTTL: 300000, ...options });
  }

  /**
   * Get specific SEU by ID
   * @param {string} seuId - SEU ID
   * @returns {Promise<Object>} SEU object
   */
  async getSEU(seuId, options = {}) {
    return this.get(`/seus/${seuId}`, {}, { cache: true, cacheTTL: 300000, ...options });
  }

  /**
   * Get energy data for SEU
   * @param {string} seuId - SEU ID
   * @param {Object} params - Query parameters
   * @param {string} params.energy_source - Energy source (electricity, natural_gas, etc.)
   * @param {string} params.duration - Time range (1h, 24h, 7d, 30d)
   * @param {string} params.start_date - Start ISO date (optional)
   * @param {string} params.end_date - End ISO date (optional)
   * @returns {Promise<Object>} Energy data with timestamps and values
   */
  async getEnergyData(seuId, params = {}, options = {}) {
    return this.get(`/seus/${seuId}/energy`, params, { cache: true, cacheTTL: 60000, ...options });
  }

  /**
   * Train baseline model for SEU
   * @param {string} seuId - SEU ID
   * @param {Object} body - Training parameters
   * @param {string} body.energy_source - Energy source
   * @param {number} body.training_weeks - Weeks of data (default: 4)
   * @param {string} body.model_type - Model type (linear_regression, etc.)
   * @returns {Promise<Object>} Training results
   */
  async trainBaseline(seuId, body = {}, options = {}) {
    return this.post(`/baseline/train-seu/${seuId}`, body, options);
  }

  /**
   * Get baseline prediction for SEU
   * @param {string} seuId - SEU ID
   * @param {Object} params - Prediction parameters
   * @param {string} params.energy_source - Energy source
   * @param {string} params.duration - Time range
   * @returns {Promise<Object>} Prediction data
   */
  async getBaseline(seuId, params = {}, options = {}) {
    return this.get(`/baseline/${seuId}/predict`, params, { cache: true, cacheTTL: 60000, ...options });
  }

  /**
   * Get energy opportunities for SEU
   * @param {string} seuId - SEU ID
   * @param {Object} params - Query parameters
   * @param {string} params.energy_source - Energy source (optional)
   * @param {number} params.threshold - Min savings threshold in kWh
   * @returns {Promise<Array>} Array of opportunity objects
   */
  async getOpportunities(seuId, params = {}, options = {}) {
    return this.get(`/performance-engine/opportunities/${seuId}`, params, { cache: true, cacheTTL: 300000, ...options });
  }

  /**
   * Get KPIs for SEU
   * @param {string} seuId - SEU ID
   * @param {Object} params - Query parameters
   * @param {string} params.energy_source - Energy source (optional)
   * @param {string} params.duration - Time range
   * @returns {Promise<Object>} KPI metrics
   */
  async getKPIs(seuId, params = {}, options = {}) {
    return this.get(`/seus/${seuId}/kpis`, params, { cache: true, cacheTTL: 60000, ...options });
  }

  /**
   * Get anomalies for SEU
   * @param {string} seuId - SEU ID
   * @param {Object} params - Query parameters
   * @param {string} params.severity - Severity filter (low, medium, high, critical)
   * @param {string} params.duration - Time range
   * @param {number} params.limit - Max results
   * @returns {Promise<Object>} Anomalies with pagination
   */
  async getAnomalies(seuId, params = {}, options = {}) {
    return this.get(`/anomaly/detect/${seuId}`, params, options);
  }

  /**
   * Get forecast for SEU
   * @param {string} seuId - SEU ID
   * @param {Object} params - Query parameters
   * @param {string} params.energy_source - Energy source
   * @param {number} params.horizon_hours - Forecast horizon (default: 24)
   * @returns {Promise<Object>} Forecast data
   */
  async getForecast(seuId, params = {}, options = {}) {
    return this.get(`/forecast/${seuId}`, params, { cache: true, cacheTTL: 300000, ...options });
  }

  /**
   * Get model performance metrics
   * @param {string} seuId - SEU ID
   * @param {Object} params - Query parameters
   * @param {string} params.energy_source - Energy source
   * @param {string} params.model_type - Model type filter
   * @returns {Promise<Object>} Model performance data
   */
  async getModelPerformance(seuId, params = {}, options = {}) {
    return this.get(`/model-performance/${seuId}`, params, { cache: true, cacheTTL: 60000, ...options });
  }

  /* ============================================================================
     UTILITY METHODS
     ========================================================================= */

  /**
   * Clear all cached responses
   */
  clearCache() {
    this.cache.clear();
    this.log('Cache cleared');
  }

  /**
   * Cancel specific request by ID
   * @param {string} requestId - Request ID
   */
  cancelRequest(requestId) {
    const controller = this.abortControllers.get(requestId);
    if (controller) {
      controller.abort();
      this.abortControllers.delete(requestId);
      this.log('Request cancelled:', requestId);
    }
  }

  /**
   * Cancel all pending requests
   */
  cancelAll() {
    for (const [id, controller] of this.abortControllers.entries()) {
      controller.abort();
    }
    this.abortControllers.clear();
    this.log('All requests cancelled');
  }

  /**
   * Sleep utility for retry delays
   * @param {number} ms - Milliseconds to sleep
   * @returns {Promise} Promise that resolves after delay
   */
  sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  /**
   * Log helper
   * @param {...any} args - Log arguments
   */
  log(...args) {
    if (this.enableLogging) {
      console.log('[APIClient]', ...args);
    }
  }
}

/**
 * @class APIError
 * @description Custom error class for API errors
 */
export class APIError extends Error {
  /**
   * @param {string} message - Error message
   * @param {number} status - HTTP status code
   * @param {boolean} retryable - Whether error is retryable
   */
  constructor(message, status, retryable = false) {
    super(message);
    this.name = 'APIError';
    this.status = status;
    this.retryable = retryable;
  }
}

// Create singleton instance
const apiClient = new APIClient('/api/v1', { enableLogging: false });
export { apiClient };
