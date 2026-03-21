import * as path from 'node:path';

export const asset = (name: string) => path.resolve(`assets/${name}`);

export const NEWS_URL = 'file://' + path.resolve('pages/news.html');

export const TARGET_STORY_ID = '#story-harbor-dossier';
export const DISTRACTOR_STORY_ID = '#story-trains-briefing';
