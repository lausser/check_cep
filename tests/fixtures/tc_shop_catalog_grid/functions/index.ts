import * as path from 'node:path';

export const asset = (name: string) => path.resolve(`assets/${name}`);

export const CATALOG_URL = 'file://' + path.resolve('pages/catalog.html');

export const TARGET_CARD_ID = '#card-nimbus-lamp';
export const TARGET_STATUS_ID = '#status-nimbus-lamp';
export const DISTRACTOR_CARD_ID = '#card-pixel-speaker';
