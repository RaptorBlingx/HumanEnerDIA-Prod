/**
 * LoadingOrchestrator Utility
 * 
 * @file loading-orchestrator.js
 * @description Coordinates progressive loading of multiple page widgets/components
 * @version 3.0.0
 * @date November 10, 2025
 */

/**
 * @class LoadingOrchestrator
 * @description Manages loading states for multiple async tasks with priority-based execution
 * 
 * Use Cases:
 * - Dashboard: Load KPI cards → charts → tables in sequence
 * - Baseline page: Load SEUs → training history → model metrics
 * - Prevents "flash of empty content"
 * - Shows incremental progress to users
 * 
 * @example
 * const orchestrator = new LoadingOrchestrator({
 *   onProgress: (completed, total) => {
 *     console.log(`${completed}/${total} widgets loaded`);
 *   }
 * });
 * 
 * orchestrator.addTask('kpis', fetchKPIs, { priority: 1 });
 * orchestrator.addTask('chart', fetchChartData, { priority: 2 });
 * await orchestrator.executeAll();
 */
export default class LoadingOrchestrator {
  /**
   * @param {Object} options - Configuration options
   * @param {Function} options.onProgress - Progress callback (completed, total)
   * @param {Function} options.onTaskStart - Task start callback (taskId)
   * @param {Function} options.onTaskComplete - Task complete callback (taskId, result)
   * @param {Function} options.onTaskError - Task error callback (taskId, error)
   * @param {number} options.concurrency - Max concurrent tasks (default: 3)
   */
  constructor(options = {}) {
    this.tasks = new Map();
    this.results = new Map();
    this.errors = new Map();
    
    this.onProgress = options.onProgress || (() => {});
    this.onTaskStart = options.onTaskStart || (() => {});
    this.onTaskComplete = options.onTaskComplete || (() => {});
    this.onTaskError = options.onTaskError || (() => {});
    this.concurrency = options.concurrency || 3;
    
    this.completed = 0;
    this.isExecuting = false;
  }

  /**
   * Add task to orchestrator
   * @param {string} id - Unique task identifier
   * @param {Function} taskFn - Async function to execute
   * @param {Object} options - Task options
   * @param {number} options.priority - Execution priority (1=highest, default: 10)
   * @param {number} options.timeout - Task timeout in ms (default: 30000)
   * @param {Array} options.dependencies - Task IDs that must complete first
   * @param {boolean} options.critical - If true, failure stops all execution
   */
  addTask(id, taskFn, options = {}) {
    if (this.tasks.has(id)) {
      console.warn(`[LoadingOrchestrator] Task "${id}" already exists, overwriting`);
    }
    
    this.tasks.set(id, {
      id,
      taskFn,
      priority: options.priority || 10,
      timeout: options.timeout || 30000,
      dependencies: options.dependencies || [],
      critical: options.critical || false,
      status: 'pending' // pending → running → completed | failed
    });
  }

  /**
   * Execute all tasks in priority order
   * @returns {Promise<Object>} Results map
   */
  async executeAll() {
    if (this.isExecuting) {
      throw new Error('LoadingOrchestrator is already executing');
    }
    
    this.isExecuting = true;
    this.completed = 0;
    this.results.clear();
    this.errors.clear();
    
    try {
      const sortedTasks = this.getSortedTasks();
      await this.executeBatch(sortedTasks);
      
      return {
        success: true,
        results: Object.fromEntries(this.results),
        errors: Object.fromEntries(this.errors)
      };
    } catch (error) {
      console.error('[LoadingOrchestrator] Critical task failed:', error);
      return {
        success: false,
        results: Object.fromEntries(this.results),
        errors: Object.fromEntries(this.errors),
        criticalError: error.message
      };
    } finally {
      this.isExecuting = false;
    }
  }

  /**
   * Get tasks sorted by priority (with dependency resolution)
   * @returns {Array} Sorted task objects
   */
  getSortedTasks() {
    const tasks = Array.from(this.tasks.values());
    
    // Topological sort for dependencies
    const visited = new Set();
    const sorted = [];
    
    const visit = (task) => {
      if (visited.has(task.id)) return;
      visited.add(task.id);
      
      // Visit dependencies first
      for (const depId of task.dependencies) {
        const depTask = this.tasks.get(depId);
        if (depTask) {
          visit(depTask);
        }
      }
      
      sorted.push(task);
    };
    
    for (const task of tasks) {
      visit(task);
    }
    
    // Within same dependency level, sort by priority
    return sorted.sort((a, b) => a.priority - b.priority);
  }

  /**
   * Execute tasks in batches respecting concurrency limit
   * @param {Array} tasks - Sorted task array
   */
  async executeBatch(tasks) {
    const queue = [...tasks];
    const running = new Map();
    
    while (queue.length > 0 || running.size > 0) {
      // Fill up to concurrency limit
      while (running.size < this.concurrency && queue.length > 0) {
        const task = queue.shift();
        
        // Check if dependencies are met
        if (!this.areDependenciesMet(task)) {
          queue.push(task); // Re-queue
          continue;
        }
        
        const promise = this.executeTask(task);
        running.set(task.id, promise);
      }
      
      // Wait for any task to complete
      if (running.size > 0) {
        await Promise.race(running.values());
        
        // Remove completed tasks
        for (const [id, promise] of running.entries()) {
          const task = this.tasks.get(id);
          if (task.status !== 'running') {
            running.delete(id);
          }
        }
      }
    }
  }

  /**
   * Check if task dependencies are satisfied
   * @param {Object} task - Task object
   * @returns {boolean} True if dependencies met
   */
  areDependenciesMet(task) {
    for (const depId of task.dependencies) {
      const depTask = this.tasks.get(depId);
      if (!depTask || depTask.status !== 'completed') {
        return false;
      }
    }
    return true;
  }

  /**
   * Execute single task with timeout
   * @param {Object} task - Task object
   */
  async executeTask(task) {
    task.status = 'running';
    this.onTaskStart(task.id);
    
    try {
      const result = await this.withTimeout(
        task.taskFn(),
        task.timeout,
        `Task "${task.id}" timed out after ${task.timeout}ms`
      );
      
      task.status = 'completed';
      this.results.set(task.id, result);
      this.completed++;
      
      this.onTaskComplete(task.id, result);
      this.onProgress(this.completed, this.tasks.size);
      
      return result;
    } catch (error) {
      task.status = 'failed';
      this.errors.set(task.id, error.message);
      this.completed++;
      
      this.onTaskError(task.id, error);
      this.onProgress(this.completed, this.tasks.size);
      
      if (task.critical) {
        throw new Error(`Critical task "${task.id}" failed: ${error.message}`);
      }
      
      return null;
    }
  }

  /**
   * Execute promise with timeout
   * @param {Promise} promise - Promise to execute
   * @param {number} timeoutMs - Timeout in milliseconds
   * @param {string} errorMessage - Error message on timeout
   * @returns {Promise} Promise that rejects on timeout
   */
  withTimeout(promise, timeoutMs, errorMessage) {
    return Promise.race([
      promise,
      new Promise((_, reject) => {
        setTimeout(() => reject(new Error(errorMessage)), timeoutMs);
      })
    ]);
  }

  /**
   * Get task result by ID
   * @param {string} id - Task ID
   * @returns {*} Task result or null
   */
  getResult(id) {
    return this.results.get(id) || null;
  }

  /**
   * Get task error by ID
   * @param {string} id - Task ID
   * @returns {string|null} Error message or null
   */
  getError(id) {
    return this.errors.get(id) || null;
  }

  /**
   * Check if specific task succeeded
   * @param {string} id - Task ID
   * @returns {boolean} True if task completed successfully
   */
  isTaskSuccessful(id) {
    const task = this.tasks.get(id);
    return task && task.status === 'completed';
  }

  /**
   * Get execution statistics
   * @returns {Object} Stats object
   */
  getStats() {
    const total = this.tasks.size;
    const completed = Array.from(this.tasks.values()).filter(t => t.status === 'completed').length;
    const failed = Array.from(this.tasks.values()).filter(t => t.status === 'failed').length;
    const pending = Array.from(this.tasks.values()).filter(t => t.status === 'pending').length;
    
    return {
      total,
      completed,
      failed,
      pending,
      successRate: total > 0 ? (completed / total * 100).toFixed(1) : 0
    };
  }

  /**
   * Reset orchestrator state
   */
  reset() {
    this.tasks.clear();
    this.results.clear();
    this.errors.clear();
    this.completed = 0;
    this.isExecuting = false;
  }

  /**
   * Cancel all pending tasks
   */
  cancel() {
    for (const [id, task] of this.tasks.entries()) {
      if (task.status === 'pending') {
        task.status = 'failed';
        this.errors.set(id, 'Task cancelled');
      }
    }
    this.isExecuting = false;
  }
}
