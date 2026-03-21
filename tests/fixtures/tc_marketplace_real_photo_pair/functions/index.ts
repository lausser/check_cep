import * as path from 'node:path';

export const asset = (name: string) => path.resolve(`assets/${name}`);

export const MARKETPLACE_URL = 'file://' + path.resolve('pages/marketplace.html');

export const TARGET_TILE_ID = '#tile-salon-air-01';
export const DISTRACTOR_TILE_ID = '#tile-salon-air-02';
export const TARGET_STATUS_ID = '#status-salon-air-01';
export const PREVIEW_CLICK_OFFSET = { x: 30, y: 30 };
