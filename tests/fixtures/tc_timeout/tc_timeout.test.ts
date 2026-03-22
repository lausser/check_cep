import { test } from '@playwright/test';

test('test that never finishes', async () => {
  // A promise that never resolves — hangs until the container timeout kills us.
  // (Using a non-routable IP is unreliable: some kernels send RST immediately.)
  await new Promise(() => {});
});
