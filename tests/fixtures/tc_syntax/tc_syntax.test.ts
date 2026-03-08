import { test, expect } from '@playwright/test';

test('broken syntax', async ({ page }) => {
  const obj = {
    key: 'value'
  // missing closing brace — TypeScript compiler error
;
