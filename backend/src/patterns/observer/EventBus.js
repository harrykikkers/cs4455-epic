const logger = require('../../utils/logger');

/**
 * GoF Observer pattern — EventBus
 *
 * Decouples producers from consumers. When a message is sent, the
 * MessageService emits 'message:sent' — the BlockchainService and any
 * future audit/notification listeners subscribe independently.
 * Neither knows the other exists.
 *
 * Why here: The spec requires blockchain digest recording when messages
 * are sent, but coupling MessageService directly to BlockchainService
 * would violate single-responsibility. The EventBus lets them evolve
 * independently.
 */
class EventBus {
  constructor() {
    this._listeners = new Map();
  }

  /**
   * Subscribe a handler to an event.
   * @param {string} event - e.g. 'message:sent', 'user:registered'
   * @param {Function} handler - async-safe callback
   */
  on(event, handler) {
    if (!this._listeners.has(event)) {
      this._listeners.set(event, []);
    }
    this._listeners.get(event).push(handler);
    logger.debug(`EventBus: subscribed to "${event}"`);
  }

  /**
   * Remove a specific handler.
   */
  off(event, handler) {
    const handlers = this._listeners.get(event);
    if (handlers) {
      this._listeners.set(
        event,
        handlers.filter((h) => h !== handler)
      );
    }
  }

  /**
   * Emit an event to all subscribers.
   * Handlers run concurrently; failures are logged but don't propagate
   * (a blockchain write failure shouldn't prevent message delivery).
   */
  async emit(event, payload) {
    const handlers = this._listeners.get(event) || [];
    logger.debug(`EventBus: emitting "${event}" to ${handlers.length} listener(s)`);

    const results = await Promise.allSettled(
      handlers.map((h) => h(payload))
    );

    for (const result of results) {
      if (result.status === 'rejected') {
        logger.error(`EventBus handler error on "${event}":`, result.reason);
      }
    }
  }
}

// Singleton instance — shared across the application
const eventBus = new EventBus();

module.exports = eventBus;
