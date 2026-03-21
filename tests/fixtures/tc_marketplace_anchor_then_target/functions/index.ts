import * as path from 'node:path';

export const asset = (name: string) => path.resolve(`assets/${name}`);

export const MARKETPLACE_URL = 'file://' + path.resolve('pages/marketplace.html');

export const TARGET_TILE_ID = '#tile-aurora-supersonic';
export const DISTRACTOR_TILE_ID = '#tile-aurora-travel-pro';
export const TARGET_STATUS_ID = '#status-aurora-supersonic';
