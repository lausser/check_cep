/**
 * patch-lightpanda.js - CJS monkey-patch for Playwright CDP redirection.
 *
 * Loaded via NODE_OPTIONS=--require when BROWSER=lightpanda.
 * Replaces chromium.launch() and chromium.launchPersistentContext() with
 * chromium.connectOverCDP() so user test files need zero changes.
 *
 * Lightpanda only supports a single browser context and does not implement
 * all CDP emulation methods (e.g. Emulation.setUserAgentOverride).
 * To work around this, browser.newContext() is overridden to return
 * the default context that connectOverCDP provides.
 *
 * Patching playwright-core is sufficient: both `playwright` and
 * `@playwright/test` delegate to the same chromium object.
 */
'use strict';

const CDP_ENDPOINT = 'http://127.0.0.1:9222';

/**
 * Connect to the Lightpanda CDP endpoint and patch the returned browser
 * so that newContext() returns the single default context instead of
 * attempting to create a new one (which triggers unsupported CDP methods).
 */
async function connectAndPatch() {
  const pw = require('playwright-core');
  const browser = await pw.chromium.connectOverCDP(CDP_ENDPOINT);
  const defaultContext = browser.contexts()[0];

  browser.newContext = async function patchedNewContext(_options) {
    return defaultContext;
  };

  return browser;
}

try {
  const pw = require('playwright-core');
  const chromium = pw.chromium;

  chromium.launch = async function patchedLaunch(_options) {
    console.log('[CEPDBG] Overriding chromium.launch -> connectOverCDP(' + CDP_ENDPOINT + ')');
    return connectAndPatch();
  };

  chromium.launchPersistentContext = async function patchedLaunchPersistent(_userDataDir, _options) {
    console.log('[CEPDBG] Overriding chromium.launchPersistentContext -> connectOverCDP(' + CDP_ENDPOINT + ')');
    const browser = await connectAndPatch();
    return browser.contexts()[0];
  };

  console.log('[CEPDBG] Playwright monkey-patch loaded: chromium will use Lightpanda CDP');
} catch (err) {
  console.log('[CEP] Failed to patch Playwright for Lightpanda: ' + err.message);
  process.exit(1);
}
