import * as path from 'node:path';

export const asset = (name: string) => path.resolve(`assets/${name}`);

export const MARKETPLACE_URL = 'file://' + path.resolve('pages/marketplace.html');

export const TARGET_TILE_ID = '#tile-aurora-hairdryer';
export const TARGET_STATUS_ID = '#status-aurora-hairdryer';
export const DISTRACTOR_TILE_ID = '#tile-aurora-travel-dryer';

export const TILE_CLICK_OFFSET = { x: 95, y: 95 };
