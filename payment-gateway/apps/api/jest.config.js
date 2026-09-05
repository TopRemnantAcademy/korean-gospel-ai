module.exports = {
  preset: 'ts-jest',
  testEnvironment: 'node',
  testMatch: ['**/tests/**/*.test.ts'],
  verbose: true,
  moduleNameMapper: {
    '^@gospel-pay/shared$': '<rootDir>/../../packages/shared/src',
  },
};
