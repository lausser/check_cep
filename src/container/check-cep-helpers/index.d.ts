export function getTimestamp(): string;
export function cepLog(message: string): void;
export function cepLogLocated(target: string): void;
export function cepLogFound(value: string): void;
export function cepLogType(target: string, value: string): void;
export function cepLogPress(target: string): void;
export function cepLogWait(durationMs: number, reason: string): void;
export function cepLogUrl(page: any): void;
export function cepDebug(message: string): void;
