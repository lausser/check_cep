/**
 * Shared helpers for tc_vision_example_console.
 *
 * Demonstrates the functions/ convention: reusable utilities that are
 * imported by test files but ignored by run.py's test discovery.
 */
import * as path from 'node:path';

/** Resolve a template image from the committed assets/ directory. */
export const asset = (name: string) => path.resolve(`assets/${name}`);

/** URL for the local console page. */
export const CONSOLE_URL = 'file://' + path.resolve('pages/console.html');
