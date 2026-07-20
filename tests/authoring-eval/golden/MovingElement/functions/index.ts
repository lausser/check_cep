import * as path from 'node:path';
import { pathToFileURL } from 'node:url';

// Resolve the shared sample-app probe page (single source of truth).
const SAMPLE_APP = path.resolve(__dirname, '../../../sample-app');

export const PAGE_URL = pathToFileURL(
  path.join(SAMPLE_APP, 'probes/moving-element/index.html'),
).href;

export const asset = (name: string) => path.resolve(__dirname, '../assets/' + name);
