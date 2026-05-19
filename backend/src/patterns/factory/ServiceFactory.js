const { Argon2Strategy, Keccak256Strategy } = require('../strategy/HashStrategy');
const defaultEventBus = require('../observer/EventBus');

const UserRepository = require('../../repositories/UserRepository');
const MessageRepository = require('../../repositories/MessageRepository');
const KeyRepository = require('../../repositories/KeyRepository');

const AuthService = require('../../services/AuthService');
const MessageService = require('../../services/MessageService');
const BlockchainService = require('../../services/BlockchainService');
const KeyService = require('../../services/KeyService');

/**
 * GoF Factory pattern — ServiceFactory
 *
 * Centralises the creation of service objects with their dependencies
 * (repositories, strategies, event bus). Controllers call the factory
 * instead of manually wiring dependencies — this keeps controllers thin
 * and makes the dependency graph explicit in one place.
 *
 * Why here: Each service needs a specific repository + strategy combo.
 * Without a factory, every controller would duplicate the wiring logic.
 * The factory also makes it trivial to swap in mock dependencies for testing.
 */
class ServiceFactory {
  constructor(dbPool, eventBus = defaultEventBus) {
    this._pool = dbPool;
    this._eventBus = eventBus;
    this._cache = new Map();
  }

  /**
   * Lazily constructs and caches MessageRepository — MessageService and
   * BlockchainService both depend on it, and they need the same instance
   * so writes from the blockchain observer affect the same pool.
   */
  _messageRepo() {
    if (!this._cache.has('messageRepo')) {
      this._cache.set('messageRepo', new MessageRepository(this._pool));
    }
    return this._cache.get('messageRepo');
  }

  /**
   * Returns a cached singleton per service type.
   * Services are stateless, so sharing instances is safe.
   */
  getAuthService() {
    if (!this._cache.has('auth')) {
      const userRepo = new UserRepository(this._pool);
      const hashStrategy = new Argon2Strategy();
      this._cache.set('auth', new AuthService(userRepo, hashStrategy));
    }
    return this._cache.get('auth');
  }

  getMessageService() {
    if (!this._cache.has('message')) {
      this._cache.set('message', new MessageService(this._messageRepo(), this._eventBus));
    }
    return this._cache.get('message');
  }

  getBlockchainService() {
    if (!this._cache.has('blockchain')) {
      const hashStrategy = new Keccak256Strategy();
      this._cache.set('blockchain', new BlockchainService(hashStrategy, this._eventBus, this._pool));
    }
    return this._cache.get('blockchain');
  }

  getKeyService() {
    if (!this._cache.has('key')) {
      const keyRepo = new KeyRepository(this._pool);
      this._cache.set('key', new KeyService(keyRepo));
    }
    return this._cache.get('key');
  }
}

module.exports = ServiceFactory;
