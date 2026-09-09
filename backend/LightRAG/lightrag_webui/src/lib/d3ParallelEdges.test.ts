import { describe, expect, test } from 'bun:test'
import {
  computeMirofishCurvature,
  mirofishLinkPath,
  trimLinkEndpoints
} from '@/lib/d3ParallelEdges'

describe('d3ParallelEdges', () => {
  test('trimLinkEndpoints shortens line by node radius', () => {
    const trimmed = trimLinkEndpoints(0, 0, 100, 0, 10)
    expect(trimmed.sx).toBeCloseTo(10)
    expect(trimmed.sy).toBeCloseTo(0)
    expect(trimmed.tx).toBeCloseTo(90)
    expect(trimmed.ty).toBeCloseTo(0)
  })

  test('mirofishLinkPath uses straight segment when curvature is zero', () => {
    const path = mirofishLinkPath(
      { sx: 0, sy: 0, tx: 100, ty: 0 },
      { curvature: 0, pairIndex: 0, pairTotal: 1, isSelfLoop: false }
    )
    expect(path).toBe('M0,0 L100,0')
  })

  test('computeMirofishCurvature fans parallel edges', () => {
    const left = computeMirofishCurvature('a', 'b', 0, 3)
    const right = computeMirofishCurvature('a', 'b', 2, 3)
    expect(left).toBeLessThan(0)
    expect(right).toBeGreaterThan(0)
  })
})
