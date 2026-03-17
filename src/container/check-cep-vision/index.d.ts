export type RegionPreset = 'header' | 'main' | 'footer' | 'topLeft' | 'topRight' | 'left' | 'right';

export interface RectRegion {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface ClickOffset {
  x: number;
  y: number;
}

export interface VisionOptions {
  region?: RegionPreset | RectRegion;
  fullPage?: boolean;
  confidence?: number;
  ambiguityGap?: number;
  timeoutMs?: number;
  pollMs?: number;
  clickOffset?: ClickOffset;
  debugDir?: string;
  debugLabel?: string;
  scales?: number[];
  maxCandidates?: number;
  highlightMs?: number;
  highlightColor?: string;
  highlightFillColor?: string;
  scrollIntoView?: boolean;
}

export interface MatchCandidate {
  x: number;
  y: number;
  width: number;
  height: number;
  score: number | null;
  scale: number;
  colorScore: number | null;
  combinedScore: number | null;
  centerX: number;
  centerY: number;
}

export interface MatchResult {
  found: boolean;
  reason: string;
  confidence: number;
  ambiguityGap: number;
  region: RectRegion | null;
  requestedRegion: RectRegion | null;
  effectiveRegion: RectRegion | null;
  regionMode: string;
  regionWasClipped: boolean;
  bestCandidate: MatchCandidate | null;
  bestCandidateLocal: MatchCandidate | null;
  secondCandidate: MatchCandidate | null;
  secondCandidateLocal: MatchCandidate | null;
  message: string;
}

export interface ClickResult extends MatchResult {
  clickPoint: {
    x: number;
    y: number;
  };
}

export interface StrategyResult {
  strategy: 'vision' | 'dom';
  result?: ClickResult;
}

export interface VisionConstants {
  DEFAULT_CONFIDENCE: number;
  DEFAULT_TIMEOUT_MS: number;
  DEFAULT_POLL_MS: number;
  DEFAULT_AMBIGUITY_GAP: number;
  DEFAULT_SCALES: number[];
  DEFAULT_SCORE_WEIGHTS: {
    gray: number;
    color: number;
  };
}

export interface VisionApi {
  /** Returns true when the current browser can produce screenshots (false for Lightpanda). */
  canScreenshot(): boolean;
  locateByImage(page: any, templatePath: string, options?: VisionOptions): Promise<MatchResult>;
  waitForImage(page: any, templatePath: string, options?: VisionOptions): Promise<MatchResult>;
  existsByImage(page: any, templatePath: string, options?: VisionOptions): Promise<boolean>;
  highlightLocator(locator: any, options?: VisionOptions): Promise<{ strategy: 'dom' }>;
  highlightFirstVisible(candidates: any[], options?: VisionOptions): Promise<{ strategy: 'dom' }>;
  highlightByImage(page: any, templatePath: string, options?: VisionOptions): Promise<MatchResult>;
  clickFirstVisible(candidates: any[]): Promise<{ strategy: 'dom' }>;
  fillFirstVisible(page: any, selectors: string[], value: string, options?: VisionOptions): Promise<{ strategy: 'dom' }>;
  clickByImageOr(page: any, templatePath: string, candidates: any[], options?: VisionOptions): Promise<StrategyResult>;
  typeByImageOr(page: any, templatePath: string, text: string, selectors: string[], options?: VisionOptions): Promise<StrategyResult>;
  clickByImage(page: any, templatePath: string, options?: VisionOptions): Promise<ClickResult>;
  typeByImage(page: any, templatePath: string, text: string, options?: VisionOptions): Promise<ClickResult>;
  clickBestEffort(locator: any, options?: VisionOptions): Promise<{ strategy: 'dom' }>;
  typeBestEffort(locator: any, text: string, options?: VisionOptions): Promise<{ strategy: 'dom' }>;
  fillBestEffort(locator: any, value: string, options?: VisionOptions): Promise<{ strategy: 'dom' }>;
  constants: VisionConstants;
}

export const vision: VisionApi;
