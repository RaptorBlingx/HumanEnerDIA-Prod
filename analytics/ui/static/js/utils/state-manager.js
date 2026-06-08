/**
 * StateManager - Centralized state persistence with TTL
 * 
 * @file state-manager.js
 * @description localStorage wrapper with automatic expiration and versioning
 * @version 3.0.0
 * @date November 10, 2025
 * 
 * @example
 * // Save data with 5-minute TTL
 * StateManager.set('seu_selection', { seuName: 'Compressor-1' }, 300);
 * 
 * // Retrieve data (null if expired)
 * const data = StateManager.get('seu_selection');
 * 
 * // Clear all EnMS data
 * StateManager.clearAll();
 */

class StateManager {
  /**
   * Get item from localStorage with TTL validation
   * 
   * @param {string} key - Storage key (without enms_ prefix)
   * @param {number} version - Schema version (default: 1)
   * @returns {*} Data or null if expired/not found
   */
  static get(key, version = 1) {
    const storageKey = `enms_${key}_v${version}`;
    const item = localStorage.getItem(storageKey);
    
    if (!item) return null;
    
    try {
      const parsed = JSON.parse(item);
      const now = Math.floor(Date.now() / 1000);
      
      // Check if expired
      if (parsed.timestamp + parsed.ttl < now) {
        console.debug(`[StateManager] Cache expired: ${key}`);
        this.remove(key, version);
        return null;
      }
      
      console.debug(`[StateManager] Cache hit: ${key}`, parsed.data);
      return parsed.data;
    } catch (error) {
      console.error(`[StateManager] Parse error for ${key}:`, error);
      this.remove(key, version);
      return null;
    }
  }
  
  /**
   * Set item in localStorage with TTL
   * 
   * @param {string} key - Storage key (without enms_ prefix)
   * @param {*} data - Data to store
   * @param {number} ttl - Time-to-live in seconds (default: 1 hour)
   * @param {number} version - Schema version (default: 1)
   * @returns {boolean} Success status
   */
  static set(key, data, ttl = 3600, version = 1) {
    const storageKey = `enms_${key}_v${version}`;
    const item = {
      data,
      timestamp: Math.floor(Date.now() / 1000),
      ttl,
      version
    };
    
    try {
      localStorage.setItem(storageKey, JSON.stringify(item));
      console.debug(`[StateManager] Cache set: ${key} (TTL: ${ttl}s)`);
      return true;
    } catch (error) {
      console.error(`[StateManager] Storage error for ${key}:`, error);
      
      // Handle quota exceeded
      if (error.name === 'QuotaExceededError') {
        console.warn('[StateManager] Quota exceeded, clearing expired items...');
        this.clearExpired();
        
        // Retry after cleanup
        try {
          localStorage.setItem(storageKey, JSON.stringify(item));
          console.debug(`[StateManager] Retry successful: ${key}`);
          return true;
        } catch (retryError) {
          console.error(`[StateManager] Retry failed for ${key}:`, retryError);
          return false;
        }
      }
      
      return false;
    }
  }
  
  /**
   * Remove item from localStorage
   * 
   * @param {string} key - Storage key (without enms_ prefix)
   * @param {number} version - Schema version (default: 1)
   */
  static remove(key, version = 1) {
    const storageKey = `enms_${key}_v${version}`;
    localStorage.removeItem(storageKey);
    console.debug(`[StateManager] Cache removed: ${key}`);
  }
  
  /**
   * Clear all expired items
   * 
   * @returns {number} Number of items cleared
   */
  static clearExpired() {
    const now = Math.floor(Date.now() / 1000);
    let clearedCount = 0;
    
    // Get all keys
    const keys = Object.keys(localStorage);
    
    for (const key of keys) {
      // Only process EnMS keys
      if (!key.startsWith('enms_')) continue;
      
      try {
        const item = JSON.parse(localStorage.getItem(key));
        
        // Check if expired
        if (item.timestamp + item.ttl < now) {
          localStorage.removeItem(key);
          clearedCount++;
        }
      } catch (error) {
        // Invalid item, remove it
        localStorage.removeItem(key);
        clearedCount++;
      }
    }
    
    if (clearedCount > 0) {
      console.debug(`[StateManager] Cleared ${clearedCount} expired items`);
    }
    
    return clearedCount;
  }
  
  /**
   * Clear all EnMS storage
   * 
   * @returns {number} Number of items cleared
   */
  static clearAll() {
    const keys = Object.keys(localStorage).filter(k => k.startsWith('enms_'));
    keys.forEach(k => localStorage.removeItem(k));
    console.debug(`[StateManager] Cleared all storage (${keys.length} items)`);
    return keys.length;
  }
  
  /**
   * Invalidate cache by version bump
   * Removes all versions of a key
   * 
   * @param {string} key - Storage key (without enms_ prefix)
   */
  static invalidate(key) {
    // Remove all versions (v1 through v10)
    for (let v = 1; v <= 10; v++) {
      this.remove(key, v);
    }
    console.debug(`[StateManager] Invalidated: ${key}`);
  }
  
  /**
   * Get storage statistics
   * 
   * @returns {object} Storage stats
   */
  static getStats() {
    const keys = Object.keys(localStorage).filter(k => k.startsWith('enms_'));
    const now = Math.floor(Date.now() / 1000);
    
    let totalSize = 0;
    let expiredCount = 0;
    
    keys.forEach(key => {
      const value = localStorage.getItem(key);
      totalSize += key.length + value.length;
      
      try {
        const item = JSON.parse(value);
        if (item.timestamp + item.ttl < now) {
          expiredCount++;
        }
      } catch (error) {
        expiredCount++;
      }
    });
    
    return {
      totalItems: keys.length,
      expiredItems: expiredCount,
      totalSizeBytes: totalSize,
      totalSizeKB: (totalSize / 1024).toFixed(2)
    };
  }
  
  /**
   * Check if key exists and is valid
   * 
   * @param {string} key - Storage key (without enms_ prefix)
   * @param {number} version - Schema version (default: 1)
   * @returns {boolean} True if exists and not expired
   */
  static has(key, version = 1) {
    return this.get(key, version) !== null;
  }
}

// Auto-clear expired items on page load
if (typeof window !== 'undefined') {
  window.addEventListener('load', () => {
    StateManager.clearExpired();
  });
}

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
  module.exports = StateManager;
}
