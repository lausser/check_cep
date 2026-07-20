import { pathToFileURL } from 'node:url';
import * as path from 'node:path';

/**
 * Build a `file://` URL for a sample-app page, resolved relative to this
 * file's location (`sample-app/lib/`). Reused by the sample-app smoke tests
 * and by every golden "ideal" test so page addresses stay stable regardless
 * of the current working directory.
 *
 * @param relativePath page path relative to `sample-app/`, e.g.
 *   `journey/index.html` or `probes/ambiguous-elements/index.html`.
 */
export function pageUrl(relativePath: string): string {
  const sampleAppRoot = path.resolve(__dirname, '..');
  return pathToFileURL(path.join(sampleAppRoot, relativePath)).href;
}
