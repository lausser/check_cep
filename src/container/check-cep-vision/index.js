const fsp = require('node:fs/promises');
const path = require('node:path');
const { PNG } = require('pngjs');
const { cv } = require('opencv-wasm');

const DEFAULT_CONFIDENCE = 0.9;
const DEFAULT_TIMEOUT_MS = 1200;
const DEFAULT_POLL_MS = 100;
const DEFAULT_AMBIGUITY_GAP = 0.03;
const DEFAULT_SCALES = [0.97, 1.0, 1.03];
const DEFAULT_SCORE_WEIGHTS = { gray: 0.45, color: 0.55 };
const DEFAULT_CANDIDATE_BUFFER_MULTIPLIER = 12;

/**
 * Parse the optional highlight duration from environment configuration.
 *
 * The helper accepts a string because environment variables are string-based.
 * Invalid values are ignored so the runtime falls back to the built-in default.
 */
function parseHighlightMs(value) {
  if (value === undefined || value === null || value === '') {
    return null;
  }
  const parsed = Number.parseInt(String(value), 10);
  return Number.isFinite(parsed) ? parsed : null;
}

const ENV_HIGHLIGHT_MS = parseHighlightMs(process.env.CEP_VISION_HIGHLIGHT_MS);

const TERMINAL_REASONS = new Set([
  'invalid-size',
  'invalid-template',
  'invalid-region',
  'invalid-options',
  'scoring-failed',
  'unreadable-template',
]);

/**
 * Decode a PNG file into a plain RGBA buffer shape that can be consumed both by
 * OpenCV and by the debug-artefact drawing helpers.
 */
function decodePng(buffer) {
  const png = PNG.sync.read(buffer);
  return { width: png.width, height: png.height, data: Buffer.from(png.data) };
}

/**
 * Encode an RGBA buffer back to PNG. This is used for annotated debug images
 * after the match rectangle has been drawn onto the searched screenshot.
 */
function encodePng(image) {
  const png = new PNG({ width: image.width, height: image.height });
  png.data = Buffer.from(image.data);
  return PNG.sync.write(png);
}

/**
 * Convert an RGBA image into a grayscale OpenCV matrix.
 *
 * Grayscale is used only for the fast candidate-generation phase. Final
 * verification still uses color-aware scoring later in the pipeline.
 */
function toGrayMat(image) {
  const rgba = cv.matFromImageData({
    data: new Uint8ClampedArray(image.data.buffer, image.data.byteOffset, image.data.byteLength),
    width: image.width,
    height: image.height,
  });
  const gray = new cv.Mat();
  cv.cvtColor(rgba, gray, cv.COLOR_RGBA2GRAY, 0);
  rgba.delete();
  return gray;
}

/**
 * Normalize a scale value so it can be used as a stable cache key.
 */
function scaleKey(scale) {
  return Number(scale).toFixed(4);
}

/**
 * Resize a template image with a lightweight nearest-neighbor pass.
 *
 * The vision helper only supports a very small scale band, so a simple resizer
 * is enough and avoids pulling in a heavier image-processing dependency.
 */
function scaleImageNearest(image, scale) {
  if (scale === 1) {
    return image;
  }
  const width = Math.max(1, Math.round(image.width * scale));
  const height = Math.max(1, Math.round(image.height * scale));
  const data = Buffer.alloc(width * height * 4);
  for (let y = 0; y < height; y += 1) {
    const srcY = Math.min(image.height - 1, Math.round(y / scale));
    for (let x = 0; x < width; x += 1) {
      const srcX = Math.min(image.width - 1, Math.round(x / scale));
      const srcIdx = (srcY * image.width + srcX) * 4;
      const dstIdx = (y * width + x) * 4;
      data[dstIdx] = image.data[srcIdx];
      data[dstIdx + 1] = image.data[srcIdx + 1];
      data[dstIdx + 2] = image.data[srcIdx + 2];
      data[dstIdx + 3] = image.data[srcIdx + 3];
    }
  }
  return { width, height, data };
}

/**
 * Count opaque pixels so obviously invalid templates (for example fully
 * transparent images) can be rejected early with a clear error message.
 */
function countOpaquePixels(image) {
  let opaquePixels = 0;
  for (let index = 3; index < image.data.length; index += 4) {
    if (image.data[index] > 0) {
      opaquePixels += 1;
    }
  }
  return opaquePixels;
}

/**
 * Build a cache of scaled template variants used by the bounded scale search.
 *
 * This keeps the wait loop efficient because templates are read, validated, and
 * scaled once instead of on every polling iteration.
 */
function buildScaledTemplateCache(template, scales) {
  const cache = new Map();
  const allScales = new Set([1, ...scales]);
  for (const scale of allScales) {
    const scaledImage = scale === 1 ? template : scaleImageNearest(template, scale);
    cache.set(scaleKey(scale), {
      image: scaledImage,
      opaquePixels: countOpaquePixels(scaledImage),
    });
  }
  return cache;
}

/**
 * Compute overlap between two candidate rectangles.
 *
 * The smaller area is used as denominator so a subset candidate counts as a
 * strong overlap and can be deduplicated aggressively.
 */
function overlapRatio(a, b) {
  const x1 = Math.max(a.x, b.x);
  const y1 = Math.max(a.y, b.y);
  const x2 = Math.min(a.x + a.width, b.x + b.width);
  const y2 = Math.min(a.y + a.height, b.y + b.height);
  const width = Math.max(0, x2 - x1);
  const height = Math.max(0, y2 - y1);
  const overlap = width * height;
  if (!overlap) {
    return 0;
  }
  // Intentionally use the smaller area as denominator so a subset candidate is
  // treated as heavily overlapping and gets deduplicated.
  const area = Math.min(a.width * a.height, b.width * b.height);
  return overlap / area;
}

function insertCandidateByScore(buffer, candidate, maxEntries) {
  if (buffer.length === 0) {
    buffer.push(candidate);
    return;
  }

  let inserted = false;
  for (let index = 0; index < buffer.length; index += 1) {
    if (candidate.score > buffer[index].score) {
      buffer.splice(index, 0, candidate);
      inserted = true;
      break;
    }
  }
  if (!inserted && buffer.length < maxEntries) {
    buffer.push(candidate);
  }
  if (buffer.length > maxEntries) {
    buffer.length = maxEntries;
  }
}

/**
 * Remove heavily overlapping candidates while preserving descending score
 * order. This keeps only a small set of genuinely different match positions.
 */
function dedupeCandidates(candidates, limit, overlapThreshold) {
  const selected = [];
  for (const candidate of candidates) {
    if (selected.some((existing) => overlapRatio(existing, candidate) > overlapThreshold)) {
      continue;
    }
    selected.push(candidate);
    if (selected.length >= limit) {
      break;
    }
  }
  return selected;
}

/**
 * Collect the strongest candidate coordinates from the raw OpenCV result
 * matrix without sorting the entire matrix output.
 */
function collectTopCandidates(resultMat, width, height, scale, limit) {
  const raw = resultMat.data32F || resultMat.data64F || resultMat.data;
  const candidateBuffer = [];
  const maxEntries = Math.max(limit * DEFAULT_CANDIDATE_BUFFER_MULTIPLIER, limit);
  for (let y = 0; y < resultMat.rows; y += 1) {
    for (let x = 0; x < resultMat.cols; x += 1) {
      const score = raw[y * resultMat.cols + x];
      if (!Number.isFinite(score)) {
        continue;
      }
      insertCandidateByScore(candidateBuffer, { x, y, width, height, score, scale }, maxEntries);
    }
  }
  return dedupeCandidates(candidateBuffer, limit, 0.5);
}

/**
 * Run the fast grayscale template-matching pass across a small set of scales.
 *
 * This phase only proposes likely candidates. It does not decide the final
 * match because color is intentionally verified later.
 */
function grayscaleCandidates(source, scaledTemplates, scales, limit) {
  const sourceGray = toGrayMat(source);
  try {
    const candidates = [];
    for (const scale of scales) {
      const templateBundle = scaledTemplates.get(scaleKey(scale));
      if (!templateBundle) {
        continue;
      }
      const scaledTemplate = templateBundle.image;
      if (scaledTemplate.width > source.width || scaledTemplate.height > source.height) {
        continue;
      }
      const templateGray = toGrayMat(scaledTemplate);
      const result = new cv.Mat();
      try {
        cv.matchTemplate(sourceGray, templateGray, result, cv.TM_CCOEFF_NORMED);
        candidates.push(...collectTopCandidates(result, scaledTemplate.width, scaledTemplate.height, scale, limit));
      } finally {
        result.delete();
        templateGray.delete();
      }
    }
    candidates.sort((a, b) => b.score - a.score);
    return dedupeCandidates(candidates, limit, 0.45);
  } finally {
    sourceGray.delete();
  }
}

/**
 * Compare a candidate patch with the template using RGBA-aware per-pixel color
 * difference.
 *
 * Transparent template pixels are ignored. Out-of-bounds reads return null so
 * bad candidates never corrupt the score with NaN values.
 */
function colorSimilarity(source, template, atX, atY) {
  let weightedDiff = 0;
  let weight = 0;
  for (let y = 0; y < template.height; y += 1) {
    for (let x = 0; x < template.width; x += 1) {
      const tIdx = (y * template.width + x) * 4;
      const alpha = template.data[tIdx + 3] / 255;
      if (alpha === 0) {
        continue;
      }

      const sourceX = atX + x;
      const sourceY = atY + y;
      if (
        sourceX < 0
        || sourceY < 0
        || sourceX >= source.width
        || sourceY >= source.height
      ) {
        return null;
      }

      const sIdx = (sourceY * source.width + sourceX) * 4;
      weightedDiff += Math.abs(template.data[tIdx] - source.data[sIdx]) * alpha;
      weightedDiff += Math.abs(template.data[tIdx + 1] - source.data[sIdx + 1]) * alpha;
      weightedDiff += Math.abs(template.data[tIdx + 2] - source.data[sIdx + 2]) * alpha;
      weight += 3 * alpha;
    }
  }

  if (!weight) {
    return null;
  }
  const avgDiff = weightedDiff / weight;
  return Math.max(0, 1 - avgDiff / 255);
}

/**
 * Combine grayscale candidate quality and color verification into final ranked
 * candidates.
 *
 * The score weights are intentionally biased slightly toward color because the
 * product requirement is to respect red/blue and other visually meaningful
 * color differences.
 */
function verifyCandidates(source, scaledTemplates, candidates) {
  const verified = [];
  for (const candidate of candidates) {
    const templateBundle = scaledTemplates.get(scaleKey(candidate.scale));
    if (!templateBundle || templateBundle.opaquePixels === 0) {
      continue;
    }
    const colorScore = colorSimilarity(source, templateBundle.image, candidate.x, candidate.y);
    if (!Number.isFinite(colorScore)) {
      continue;
    }
    const combinedScore = candidate.score * DEFAULT_SCORE_WEIGHTS.gray + colorScore * DEFAULT_SCORE_WEIGHTS.color;
    verified.push({
      ...candidate,
      colorScore,
      combinedScore,
      centerX: candidate.x + Math.floor(candidate.width / 2),
      centerY: candidate.y + Math.floor(candidate.height / 2),
    });
  }
  return verified.sort((a, b) => b.combinedScore - a.combinedScore);
}

/**
 * Draw a visible rectangle around a match on a screenshot buffer. The helper
 * uses this for annotated debug artefacts.
 */
function drawRect(image, rect, rgba) {
  const left = Math.max(0, rect.x);
  const top = Math.max(0, rect.y);
  const right = Math.min(image.width - 1, rect.x + rect.width - 1);
  const bottom = Math.min(image.height - 1, rect.y + rect.height - 1);
  const points = [];
  for (let x = left; x <= right; x += 1) {
    points.push([x, top], [x, bottom]);
  }
  for (let y = top; y <= bottom; y += 1) {
    points.push([left, y], [right, y]);
  }
  for (const [x, y] of points) {
    const idx = (y * image.width + x) * 4;
    image.data[idx] = rgba[0];
    image.data[idx + 1] = rgba[1];
    image.data[idx + 2] = rgba[2];
    image.data[idx + 3] = rgba[3];
  }
}

/**
 * Normalize floating-point scores for result payloads and debug JSON.
 */
function toFixedNumber(value) {
  return Number.isFinite(value) ? Number(value.toFixed(6)) : null;
}

/**
 * Convert a result into a short human-readable reason string used in thrown
 * errors and diagnostics.
 */
function formatResultReason(result) {
  if (!result) {
    return 'unknown';
  }
  const details = [];
  if (result.message) {
    details.push(result.message);
  }
  if (result.bestCandidate && Number.isFinite(result.bestCandidate.combinedScore)) {
    details.push(`best=${result.bestCandidate.combinedScore.toFixed(4)}`);
  }
  return details.length > 0 ? `${result.reason}: ${details.join(' ')}` : result.reason;
}

/**
 * Strip internal fields and normalize score precision before exposing a
 * candidate in result objects or debug payloads.
 */
function sanitizeCandidate(candidate) {
  if (!candidate) {
    return null;
  }
  return {
    x: candidate.x,
    y: candidate.y,
    width: candidate.width,
    height: candidate.height,
    score: toFixedNumber(candidate.score),
    scale: candidate.scale,
    colorScore: toFixedNumber(candidate.colorScore),
    combinedScore: toFixedNumber(candidate.combinedScore),
    centerX: candidate.centerX,
    centerY: candidate.centerY,
  };
}

/**
 * Build the standard public result shape used by all locate/wait/click/type
 * operations.
 */
function createResult(reason, fields = {}) {
  return {
    found: reason === 'found',
    reason,
    confidence: fields.confidence ?? DEFAULT_CONFIDENCE,
    ambiguityGap: fields.ambiguityGap ?? DEFAULT_AMBIGUITY_GAP,
    region: fields.region ?? null,
    requestedRegion: fields.requestedRegion ?? null,
    effectiveRegion: fields.effectiveRegion ?? fields.region ?? null,
    regionMode: fields.regionMode ?? 'unknown',
    regionWasClipped: fields.regionWasClipped ?? false,
    bestCandidate: sanitizeCandidate(fields.bestCandidate),
    bestCandidateLocal: sanitizeCandidate(fields.bestCandidateLocal),
    secondCandidate: sanitizeCandidate(fields.secondCandidate),
    secondCandidateLocal: sanitizeCandidate(fields.secondCandidateLocal),
    message: fields.message ?? '',
  };
}

/**
 * Persist the searched region, the annotated region, and the structured match
 * metadata for troubleshooting.
 *
 * Debug artefacts are written only when requested so the default runtime stays
 * lightweight.
 */
async function writeDebugArtifacts(debugDir, label, screenshotBuffer, result) {
  if (!debugDir) {
    return;
  }
  await fsp.mkdir(debugDir, { recursive: true });
  if (screenshotBuffer) {
    const rawPath = path.join(debugDir, `${label}-region.png`);
    await fsp.writeFile(rawPath, screenshotBuffer);

    const image = decodePng(screenshotBuffer);
    if (result.bestCandidateLocal) {
      drawRect(image, result.bestCandidateLocal, [255, 64, 64, 255]);
    }
    const annotatedPath = path.join(debugDir, `${label}-annotated.png`);
    await fsp.writeFile(annotatedPath, encodePng(image));
  }

  const payload = {
    requestedRegion: result.requestedRegion,
    region: result.region,
    effectiveRegion: result.effectiveRegion,
    regionMode: result.regionMode,
    regionWasClipped: result.regionWasClipped,
    reason: result.reason,
    confidence: result.confidence,
    ambiguityGap: result.ambiguityGap,
    message: result.message,
    bestCandidate: result.bestCandidate,
    bestCandidateLocal: result.bestCandidateLocal,
    secondCandidate: result.secondCandidate,
    secondCandidateLocal: result.secondCandidateLocal,
  };
  await fsp.writeFile(path.join(debugDir, `${label}-meta.json`), JSON.stringify(payload, null, 2));
}

/**
 * Resolve the active viewport rectangle. The helper uses this as the baseline
 * coordinate space for region presets and custom region clipping.
 */
async function viewportRect(page) {
  const viewport = page.viewportSize();
  if (viewport) {
    return { x: 0, y: 0, width: viewport.width, height: viewport.height };
  }
  const size = await page.evaluate(() => ({ width: window.innerWidth, height: window.innerHeight }));
  return { x: 0, y: 0, width: size.width, height: size.height };
}

function regionsEqual(a, b) {
  return a.x === b.x && a.y === b.y && a.width === b.width && a.height === b.height;
}

/**
 * Clip a custom region to the current viewport and keep track of whether the
 * user's requested region had to be modified.
 */
function normalizeRegionRect(region, viewport) {
  const requested = {
    x: Math.round(region.x),
    y: Math.round(region.y),
    width: Math.round(region.width),
    height: Math.round(region.height),
  };

  const x = Math.max(0, Math.min(viewport.width - 1, requested.x));
  const y = Math.max(0, Math.min(viewport.height - 1, requested.y));
  const width = Math.max(0, Math.min(requested.width, viewport.width - x));
  const height = Math.max(0, Math.min(requested.height, viewport.height - y));

  return {
    requestedRegion: requested,
    effectiveRegion: { x, y, width, height },
    regionWasClipped: !regionsEqual(requested, { x, y, width, height }),
  };
}

/**
 * Resolve either a named region preset or a custom rectangle into the actual
 * screenshot area used for matching.
 *
 * The default behavior is intentionally region-first (`main`-like inset), not
 * full-page search.
 */
async function resolveRegion(page, region) {
  const viewport = await viewportRect(page);
  const defaultInset = {
    x: Math.round(viewport.width * 0.1),
    y: Math.round(viewport.height * 0.14),
    width: Math.round(viewport.width * 0.8),
    height: Math.round(viewport.height * 0.72),
  };

  if (!region) {
    const normalized = normalizeRegionRect(defaultInset, viewport);
    return {
      ...normalized,
      regionMode: 'default-main-inset',
    };
  }

  if (typeof region === 'object') {
    const normalized = normalizeRegionRect(region, viewport);
    if (normalized.effectiveRegion.width < 1 || normalized.effectiveRegion.height < 1) {
      return {
        ...normalized,
        regionMode: 'custom',
        invalidRegion: true,
      };
    }
    return {
      ...normalized,
      regionMode: 'custom',
    };
  }

  const halfWidth = Math.round(viewport.width / 2);
  const topHeight = Math.round(viewport.height * 0.35);
  const presets = {
    header: { x: 0, y: 0, width: viewport.width, height: Math.round(viewport.height * 0.18) },
    main: defaultInset,
    footer: { x: 0, y: Math.round(viewport.height * 0.8), width: viewport.width, height: Math.round(viewport.height * 0.2) },
    topLeft: { x: 0, y: 0, width: halfWidth, height: topHeight },
    topRight: { x: halfWidth, y: 0, width: viewport.width - halfWidth, height: topHeight },
    left: { x: 0, y: 0, width: halfWidth, height: viewport.height },
    right: { x: halfWidth, y: 0, width: viewport.width - halfWidth, height: viewport.height },
  };

  if (!presets[region]) {
    return {
      requestedRegion: null,
      effectiveRegion: null,
      regionMode: `invalid-preset:${region}`,
      regionWasClipped: false,
      invalidRegion: true,
    };
  }

  const normalized = normalizeRegionRect(presets[region], viewport);
  return {
    ...normalized,
    regionMode: `preset:${region}`,
  };
}

/**
 * Capture either the full page, the viewport, or a clipped region with
 * animations disabled and the caret hidden to improve visual determinism.
 */
async function captureRegion(page, effectiveRegion, fullPage) {
  if (!effectiveRegion && fullPage) {
    return page.screenshot({ type: 'png', fullPage: true, animations: 'disabled', caret: 'hide' });
  }
  if (!effectiveRegion) {
    return page.screenshot({ type: 'png', animations: 'disabled', caret: 'hide' });
  }
  return page.screenshot({
    type: 'png',
    clip: {
      x: effectiveRegion.x,
      y: effectiveRegion.y,
      width: effectiveRegion.width,
      height: effectiveRegion.height,
    },
    animations: 'disabled',
    caret: 'hide',
  });
}

/**
 * Compute the final click point. By default this is the center of the match,
 * but callers can supply an offset for composite controls such as checkbox rows
 * or label-plus-input templates.
 */
function offsetPoint(match, clickOffset) {
  if (!clickOffset) {
    return { x: match.centerX, y: match.centerY };
  }
  return {
    x: match.x + clickOffset.x,
    y: match.y + clickOffset.y,
  };
}

/**
 * Read, validate, and scale a template image for later reuse inside a wait
 * loop.
 */
async function loadTemplateBundle(templatePath, scales) {
  try {
    const template = decodePng(await fsp.readFile(templatePath));
    const opaquePixels = countOpaquePixels(template);
    if (opaquePixels === 0) {
      return {
        ok: false,
        reason: 'invalid-template',
        message: `Template has no opaque pixels: ${templatePath}`,
      };
    }
    return {
      ok: true,
      template,
      scaledTemplates: buildScaledTemplateCache(template, scales),
    };
  } catch (error) {
    return {
      ok: false,
      reason: 'unreadable-template',
      message: `Unable to read template: ${templatePath} (${error.message})`,
    };
  }
}

/**
 * Core locate implementation used by all public image-based operations.
 *
 * It handles region resolution, screenshot capture, fast candidate generation,
 * color-aware verification, ambiguity checks, and optional debug artefact
 * writing.
 */
async function locateWithTemplate(page, templateBundle, options = {}) {
  const confidence = options.confidence ?? DEFAULT_CONFIDENCE;
  const ambiguityGap = options.ambiguityGap ?? DEFAULT_AMBIGUITY_GAP;
  const scales = options.scales ?? DEFAULT_SCALES;

  if (options.fullPage && options.region) {
    const result = createResult('invalid-options', {
      confidence,
      ambiguityGap,
      message: 'Use either fullPage or region, not both in the same call.',
      regionMode: 'invalid-options',
    });
    await writeDebugArtifacts(options.debugDir, options.debugLabel || 'invalid-options', null, result);
    return result;
  }

  const resolvedRegion = options.fullPage
    ? {
        requestedRegion: null,
        effectiveRegion: null,
        regionMode: 'full-page',
        regionWasClipped: false,
        invalidRegion: false,
      }
    : await resolveRegion(page, options.region);

  if (resolvedRegion.invalidRegion) {
    const result = createResult('invalid-region', {
      confidence,
      ambiguityGap,
      requestedRegion: resolvedRegion.requestedRegion,
      effectiveRegion: resolvedRegion.effectiveRegion,
      region: resolvedRegion.effectiveRegion,
      regionMode: resolvedRegion.regionMode,
      regionWasClipped: resolvedRegion.regionWasClipped,
      message: 'Search region is invalid or fully outside the viewport.',
    });
    await writeDebugArtifacts(options.debugDir, options.debugLabel || 'invalid-region', null, result);
    return result;
  }

  const screenshotBuffer = await captureRegion(page, resolvedRegion.effectiveRegion, options.fullPage === true);
  const source = decodePng(screenshotBuffer);

  if (!templateBundle.ok) {
    const result = createResult(templateBundle.reason, {
      confidence,
      ambiguityGap,
      requestedRegion: resolvedRegion.requestedRegion,
      effectiveRegion: resolvedRegion.effectiveRegion,
      region: resolvedRegion.effectiveRegion,
      regionMode: resolvedRegion.regionMode,
      regionWasClipped: resolvedRegion.regionWasClipped,
      message: templateBundle.message,
    });
    await writeDebugArtifacts(options.debugDir, options.debugLabel || templateBundle.reason, screenshotBuffer, result);
    return result;
  }

  const template = templateBundle.template;
  if (template.width > source.width || template.height > source.height) {
    const result = createResult('invalid-size', {
      confidence,
      ambiguityGap,
      requestedRegion: resolvedRegion.requestedRegion,
      effectiveRegion: resolvedRegion.effectiveRegion,
      region: resolvedRegion.effectiveRegion,
      regionMode: resolvedRegion.regionMode,
      regionWasClipped: resolvedRegion.regionWasClipped,
      message: 'Template is larger than the searchable source image.',
    });
    await writeDebugArtifacts(options.debugDir, options.debugLabel || 'invalid-size', screenshotBuffer, result);
    return result;
  }

  const candidates = grayscaleCandidates(source, templateBundle.scaledTemplates, scales, options.maxCandidates ?? 4);
  const verified = verifyCandidates(source, templateBundle.scaledTemplates, candidates);
  const bestLocal = verified[0] || null;
  const secondLocal = verified[1] || null;

  if (candidates.length > 0 && verified.length === 0) {
    const result = createResult('scoring-failed', {
      confidence,
      ambiguityGap,
      requestedRegion: resolvedRegion.requestedRegion,
      effectiveRegion: resolvedRegion.effectiveRegion,
      region: resolvedRegion.effectiveRegion,
      regionMode: resolvedRegion.regionMode,
      regionWasClipped: resolvedRegion.regionWasClipped,
      message: 'Candidate verification could not produce a finite score.',
    });
    await writeDebugArtifacts(options.debugDir, options.debugLabel || 'scoring-failed', screenshotBuffer, result);
    return result;
  }

  const offsetX = resolvedRegion.effectiveRegion ? resolvedRegion.effectiveRegion.x : 0;
  const offsetY = resolvedRegion.effectiveRegion ? resolvedRegion.effectiveRegion.y : 0;
  const bestCandidate = bestLocal ? {
    ...bestLocal,
    x: bestLocal.x + offsetX,
    y: bestLocal.y + offsetY,
    centerX: bestLocal.centerX + offsetX,
    centerY: bestLocal.centerY + offsetY,
  } : null;
  const secondCandidate = secondLocal ? {
    ...secondLocal,
    x: secondLocal.x + offsetX,
    y: secondLocal.y + offsetY,
    centerX: secondLocal.centerX + offsetX,
    centerY: secondLocal.centerY + offsetY,
  } : null;

  const found = Boolean(bestCandidate && bestCandidate.combinedScore >= confidence);
  const ambiguous = Boolean(
    found
      && secondCandidate
      && bestCandidate.combinedScore - secondCandidate.combinedScore < ambiguityGap
  );

  const result = createResult(ambiguous ? 'ambiguous' : (found ? 'found' : 'not-found'), {
    confidence,
    ambiguityGap,
    requestedRegion: resolvedRegion.requestedRegion,
    effectiveRegion: resolvedRegion.effectiveRegion,
    region: resolvedRegion.effectiveRegion,
    regionMode: resolvedRegion.regionMode,
    regionWasClipped: resolvedRegion.regionWasClipped,
    bestCandidate,
    bestCandidateLocal: bestLocal,
    secondCandidate,
    secondCandidateLocal: secondLocal,
    message: ambiguous ? 'Multiple strong candidates remain after verification.' : '',
  });

  if (options.debugDir) {
    await writeDebugArtifacts(options.debugDir, options.debugLabel || 'match', screenshotBuffer, result);
  }
  return result;
}

function isTerminalReason(reason) {
  return TERMINAL_REASONS.has(reason);
}

/**
 * Build the thrown error text for wait-based operations. If a candidate exists,
 * the message includes the combined, color, and grayscale scores to make tuning
 * and diagnosis easier.
 */
function failureMessage(result, confidence) {
  if (result.bestCandidate && Number.isFinite(result.bestCandidate.combinedScore)) {
    return `Image match failed: reason=${result.reason} confidence=${confidence.toFixed(4)} best=${result.bestCandidate.combinedScore.toFixed(4)} color=${result.bestCandidate.colorScore.toFixed(4)} gray=${result.bestCandidate.score.toFixed(4)}`;
  }
  return `Image match failed: reason=${result.reason} confidence=${confidence.toFixed(4)} ${result.message || 'best=none'}`;
}

/**
 * Locate a template once and return the full structured result.
 */
async function locateByImage(page, templatePath, options = {}) {
  const scales = options.scales ?? DEFAULT_SCALES;
  const templateBundle = await loadTemplateBundle(templatePath, scales);
  return locateWithTemplate(page, templateBundle, options);
}

/**
 * Poll until a template match is found or the timeout is reached.
 *
 * Non-recoverable conditions (invalid template, invalid region, scoring
 * failures) stop immediately with a clear error instead of burning time in a
 * retry loop.
 */
async function waitForImage(page, templatePath, options = {}) {
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const pollMs = options.pollMs ?? DEFAULT_POLL_MS;
  const scales = options.scales ?? DEFAULT_SCALES;
  const confidence = options.confidence ?? DEFAULT_CONFIDENCE;
  const templateBundle = await loadTemplateBundle(templatePath, scales);

  const start = Date.now();
  let lastResult = null;
  while (Date.now() - start <= timeoutMs) {
    lastResult = await locateWithTemplate(page, templateBundle, { ...options, scales });
    if (lastResult.found) {
      return lastResult;
    }
    if (isTerminalReason(lastResult.reason)) {
      throw new Error(failureMessage(lastResult, confidence));
    }
    await page.waitForTimeout(pollMs);
  }
  throw new Error(failureMessage(lastResult, confidence));
}

/**
 * Convenience boolean check for presence-by-image.
 *
 * Plain `not-found` becomes `false`; invalid or ambiguous states remain errors
 * because those are operational problems, not normal absence.
 */
async function existsByImage(page, templatePath, options = {}) {
  const result = await locateByImage(page, templatePath, options);
  if (result.found) {
    return true;
  }
  if (result.reason === 'not-found') {
    return false;
  }
  throw new Error(formatResultReason(result));
}

/**
 * Show a temporary visual overlay around a match or DOM-located element.
 *
 * This intentionally imitates Sakuli's highlight behavior so headed runs are
 * easier to understand and demo.
 */
async function highlightMatchBox(page, rect, options = {}) {
  const highlightMs = options.highlightMs ?? ENV_HIGHLIGHT_MS ?? 700;
  if (!rect || !Number.isFinite(highlightMs) || highlightMs <= 0) {
    return;
  }
  const color = options.highlightColor || '#ffb703';
  const fill = options.highlightFillColor || 'rgba(255, 183, 3, 0.14)';
  await page.evaluate(async ({ x, y, width, height, color: borderColor, fill: bgFill, delay }) => {
    const overlay = document.createElement('div');
    overlay.setAttribute('data-check-cep-vision-highlight', 'true');
    overlay.style.position = 'fixed';
    overlay.style.left = `${x}px`;
    overlay.style.top = `${y}px`;
    overlay.style.width = `${width}px`;
    overlay.style.height = `${height}px`;
    overlay.style.boxSizing = 'border-box';
    overlay.style.border = `5px solid ${borderColor}`;
    overlay.style.borderRadius = '8px';
    overlay.style.background = bgFill;
    overlay.style.boxShadow = `0 0 0 3px rgba(255,255,255,0.92), 0 0 18px 6px ${borderColor}`;
    overlay.style.pointerEvents = 'none';
    overlay.style.zIndex = '2147483647';
    document.body.appendChild(overlay);
    await new Promise((resolve) => setTimeout(resolve, delay));
    overlay.remove();
  }, {
    x: rect.x,
    y: rect.y,
    width: rect.width,
    height: rect.height,
    color,
    fill,
    delay: highlightMs,
  });
}

/**
 * Highlight a single Playwright locator by drawing an overlay around its first
 * visible bounding box.
 */
async function highlightLocator(locator, options = {}) {
  if (!(await isVisibleLocator(locator))) {
    throw new Error('No visible element available for highlighting.');
  }
  const box = await locator.first().boundingBox();
  if (!box) {
    throw new Error('Unable to determine bounding box for highlight.');
  }
  const page = await locator.first().page();
  await highlightMatchBox(page, box, options);
  return { strategy: 'dom' };
}

/**
 * Highlight the first visible locator from a candidate list.
 */
async function highlightFirstVisible(candidates, options = {}) {
  for (const locator of candidates) {
    if (await isVisibleLocator(locator)) {
      return highlightLocator(locator, options);
    }
  }
  throw new Error('No visible highlight target found.');
}

/**
 * Lightweight visibility guard used by the DOM convenience helpers.
 */
async function isVisibleLocator(locator) {
  if (!locator || typeof locator.count !== 'function' || typeof locator.first !== 'function') {
    return false;
  }
  if ((await locator.count()) === 0) {
    return false;
  }
  try {
    return await locator.first().isVisible();
  } catch {
    return false;
  }
}

/**
 * Click the first visible DOM locator in the supplied list.
 *
 * This is intentionally tiny but useful for migration work where the original
 * Sakuli step already used DOM/HTML selection and the test author only wants a
 * concise "try these visible targets" helper.
 */
async function clickFirstVisible(candidates, options = {}) {
  for (const locator of candidates) {
    if (await isVisibleLocator(locator)) {
      await highlightLocator(locator, options).catch(() => undefined);
      await locator.first().click();
      return { strategy: 'dom' };
    }
  }
  throw new Error('No visible click target found.');
}

/**
 * Fill the first visible selector from a list of candidate selectors.
 */
async function fillFirstVisible(page, selectors, value, options = {}) {
  for (const selector of selectors) {
    const locator = page.locator(selector).first();
    if (await isVisibleLocator(locator)) {
      await highlightLocator(locator, options).catch(() => undefined);
      await locator.fill(value);
      return { strategy: 'dom' };
    }
  }
  throw new Error(`No visible selector found for value ${value}`);
}

/**
 * Small pass-through used to keep the image-first fallback wrappers readable.
 */
function visionOptions(options = {}) {
  return options;
}

/**
 * Image-first typing with DOM fallback.
 *
 * This is useful for migration cases where the old Sakuli step already mixed a
 * visual target with a fallback path, but the actual vision mechanics remain in
 * `typeByImage()`.
 */
async function typeByImageOr(page, templatePath, text, selectors, options = {}) {
  try {
    const result = await typeByImage(page, templatePath, text, visionOptions(options));
    return { strategy: 'vision', result };
  } catch {
    await fillFirstVisible(page, selectors, text, options);
    return { strategy: 'dom' };
  }
}

/**
 * Image-first clicking with DOM fallback.
 */
async function clickByImageOr(page, templatePath, candidates, options = {}) {
  try {
    const result = await clickByImage(page, templatePath, visionOptions(options));
    return { strategy: 'vision', result };
  } catch {
    await clickFirstVisible(candidates, options);
    return { strategy: 'dom' };
  }
}

/**
 * Locate and highlight an image match without clicking it.
 *
 * This mirrors Sakuli's visual feedback and is useful for demo runs or future
 * manual/reference documentation.
 */
async function highlightByImage(page, templatePath, options = {}) {
  const result = await waitForImage(page, templatePath, options);
  await highlightMatchBox(page, result.bestCandidate, options);
  return result;
}

/**
 * Click the best image match after waiting for it and highlighting it.
 */
async function clickByImage(page, templatePath, options = {}) {
  const result = await waitForImage(page, templatePath, options);
  await highlightMatchBox(page, result.bestCandidate, options);
  const point = offsetPoint(result.bestCandidate, options.clickOffset);
  await page.mouse.click(point.x, point.y);
  return { ...result, clickPoint: point };
}

/**
 * Type text into the best image match by clicking it first.
 */
async function typeByImage(page, templatePath, text, options = {}) {
  const clicked = await clickByImage(page, templatePath, options);
  await page.keyboard.type(text);
  return clicked;
}

module.exports = {
  vision: {
    locateByImage,
    waitForImage,
    existsByImage,
    highlightLocator,
    highlightFirstVisible,
    highlightByImage,
    clickFirstVisible,
    fillFirstVisible,
    clickByImageOr,
    typeByImageOr,
    clickByImage,
    typeByImage,
    constants: {
      DEFAULT_CONFIDENCE,
      DEFAULT_TIMEOUT_MS,
      DEFAULT_POLL_MS,
      DEFAULT_AMBIGUITY_GAP,
      DEFAULT_SCALES,
      DEFAULT_SCORE_WEIGHTS,
    },
  },
};
