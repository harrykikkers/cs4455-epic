/**
 * Jest configuration.
 *
 * Tests live under tests/ and mirror the src/ layout. Each service has an
 * accompanying `.test.js` that uses mocked repositories — no real database
 * is required to run `npm test`.
 */
module.exports = {
  testEnvironment: 'node',
  testMatch: ['<rootDir>/tests/**/*.test.js'],
  setupFiles: ['<rootDir>/tests/helpers/jest.setup.js'],
  collectCoverageFrom: [
    'src/**/*.js',
    '!src/app.js',          // boot file — exercised by integration tests
    '!src/config/**',       // env-driven, low value to mock
  ],
  coverageDirectory: 'coverage',
  coverageReporters: ['text-summary', 'html'],
  // Fail the run if any test takes longer than 10s — Argon2 verifies are slow
  // by design, so this is a sanity guard rather than a perf budget.
  testTimeout: 10000,
  // Keep Jest's noisy output focused on failures
  silent: false,
  verbose: true,
};
