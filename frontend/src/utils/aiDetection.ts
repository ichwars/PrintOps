export type AiDetectionClass = 'failure' | 'warning' | 'safe' | 'error' | 'unknown' | 'idle';

export interface AiDetection {
  class: string;
  frame_count: number;
  score: number;
  error?: string | null;
}

export function aiDetectionClass(detection?: AiDetection): AiDetectionClass {
  if (!detection) return 'idle';
  switch (detection.class) {
    case 'failure':
    case 'warning':
    case 'safe':
    case 'error':
      return detection.class;
    default:
      return 'unknown';
  }
}

export function hasAiVerdict(classification: AiDetectionClass): boolean {
  return classification === 'failure' || classification === 'warning' || classification === 'safe';
}
