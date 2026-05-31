jest.mock('argon2', () => ({
  argon2id: 2,
  hash: jest.fn(),
  verify: jest.fn(),
}));

jest.mock('../../src/config', () => ({
  argon2: {
    memoryCost: 65536,
    timeCost: 3,
    parallelism: 4,
  },
}));

const argon2 = require('argon2');
const PasswordHasher = require('../../src/services/PasswordHasher');

describe('PasswordHasher', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('sets argon2 options from config in the constructor', () => {
    const hasher = new PasswordHasher();

    expect(hasher.options).toEqual({
      type: argon2.argon2id,
      memoryCost: 65536,
      timeCost: 3,
      parallelism: 4,
    });
  });

  it('hash calls argon2.hash with password and options', async () => {
    argon2.hash.mockResolvedValue('hashed-value');

    const hasher = new PasswordHasher();
    const result = await hasher.hash('my-password');

    expect(argon2.hash).toHaveBeenCalledTimes(1);
    expect(argon2.hash).toHaveBeenCalledWith('my-password', {
      type: argon2.argon2id,
      memoryCost: 65536,
      timeCost: 3,
      parallelism: 4,
    });
    expect(result).toBe('hashed-value');
  });

  it('verify calls argon2.verify with hash first and password second', async () => {
    argon2.verify.mockResolvedValue(true);

    const hasher = new PasswordHasher();
    const result = await hasher.verify('my-password', 'stored-hash');

    expect(argon2.verify).toHaveBeenCalledTimes(1);
    expect(argon2.verify).toHaveBeenCalledWith('stored-hash', 'my-password');
    expect(result).toBe(true);
  });

  it('returns false when verification fails', async () => {
    argon2.verify.mockResolvedValue(false);

    const hasher = new PasswordHasher();
    const result = await hasher.verify('wrong-password', 'stored-hash');

    expect(result).toBe(false);
  });
});
