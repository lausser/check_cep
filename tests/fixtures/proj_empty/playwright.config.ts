import { defineConfig } from '@playwright/test';

// testDir matches nothing: the check must be UNKNOWN, not CRITICAL (FR-043).
export default defineConfig({ testDir: './nothing' });
