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
  locateByImage(page: any, templatePath: string, options?: VisionOptions): Promise<MatchResult>;
  waitForImage(page: any, templatePath: string, options?: VisionOptions): Promise<MatchResult>;
  existsByImage(page: any, templatePath: string, options?: VisionOptions): Promise<boolean>;
  clickByImage(page: any, templatePath: string, options?: VisionOptions): Promise<ClickResult>;
  typeByImage(page: any, templatePath: string, text: string, options?: VisionOptions): Promise<ClickResult>;
  constants: VisionConstants;
}

export const vision: VisionApi;
