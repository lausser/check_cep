import * as path from 'node:path';
import { pathToFileURL } from 'node:url';

// The golden test verifies against the shared sample app (single source of
// truth). In a real deployed package the journey pages travel alongside the
// test; here we resolve them relative to this file to avoid duplication/drift.
const SAMPLE_APP = path.resolve(__dirname, '../../../sample-app');

export const journeyUrl = (page: string) =>
  pathToFileURL(path.join(SAMPLE_APP, 'journey', page)).href;

export const LANDING_URL = journeyUrl('index.html');

// Demo credentials — mirror the journey .env.example (DEMO_USER / DEMO_PASS).
export const DEMO_USER = 'demo';
export const DEMO_PASS = 'Passw0rd!';

/** Strip a formatted currency string ("€ 4,250.00") to a bare number ("4250.00"). */
export const toNumber = (formatted: string): string =>
  formatted.replace(/[^\d.]/g, '');
