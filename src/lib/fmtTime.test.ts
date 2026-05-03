import { describe, expect, it } from 'vitest';
import { fmtTime } from './fmtTime';

describe('fmtTime', () => {
  it('rounds before splitting minutes and seconds', () => {
    expect(fmtTime(599.95)).toBe('10:00.0');
    expect(fmtTime(60.0)).toBe('1:00.0');
    expect(fmtTime(0.05)).toBe('0:00.1');
  });
});
