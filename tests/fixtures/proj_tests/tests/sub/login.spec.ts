import { test, expect } from '@playwright/test';
import { expectedBaseURL } from '@shared/login';

test('root config applies', async () => {
  expect(test.info().project.use.baseURL).toBe(expectedBaseURL);
  test.info().annotations.push({ type: 'perfdata_x', description: '1' });
});
