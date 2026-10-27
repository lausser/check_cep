import { test, expect } from '@playwright/test';

// spec 023 US1: --environ values reach the test as process.env, in every mode.

test('reads secret', async () => {
  expect(process.env.APP_PASSWORD).toBe('s3cret');
});

test('no implicit forwarding', async () => {
  // FR-008: only names given with --environ reach the container.
  expect(process.env.GEMINI_API_KEY).toBeUndefined();
});

test('odd value byte-for-byte', async () => {
  test.skip(process.env.CEP_ODD_VALUE === undefined, 'CEP_ODD_VALUE not passed');
  expect(process.env.CEP_ODD_VALUE).toBe('a b "c" \'d\' e=f\ng');
});

test('leaks secret into error', async () => {
  test.skip(process.env.CEP_LEAK_CHECK !== 'leakcheck-on', 'leak check off');
  // Fails on purpose: the error message contains the secret, which the
  // plugin output must mask.
  expect(process.env.APP_PASSWORD).toBe('wrong');
});
