import { describe, expect, test, beforeEach } from 'bun:test'
import {
  loadGraphLayoutCache,
  positionsFromCache,
  saveGraphLayoutCache
} from '@/lib/d3GraphLayoutCache'

describe('d3GraphLayoutCache', () => {
  const storage = new Map<string, string>()

  beforeEach(() => {
    storage.clear()
    globalThis.localStorage = {
      getItem: (key: string) => storage.get(key) ?? null,
      setItem: (key: string, value: string) => {
        storage.set(key, value)
      },
      removeItem: (key: string) => {
        storage.delete(key)
      },
      clear: () => storage.clear(),
      key: () => '',
      length: 0
    } as Storage
  })

  test('saves and loads positions for workspace + label', () => {
    saveGraphLayoutCache('task_a', '飞行员', {
      nodeFingerprint: '2:a|b',
      positions: { a: { x: 10, y: 20 }, b: { x: 30, y: 40 } }
    })
    const loaded = loadGraphLayoutCache('task_a', '飞行员')
    expect(loaded?.nodeFingerprint).toBe('2:a|b')
    expect(loaded?.positions.a).toEqual({ x: 10, y: 20 })
  })

  test('positionsFromCache rejects fingerprint mismatch', () => {
    saveGraphLayoutCache('ws', '*', {
      nodeFingerprint: '1:a',
      positions: { a: { x: 1, y: 2 } }
    })
    const cache = loadGraphLayoutCache('ws', '*')
    expect(positionsFromCache(cache, '1:a')?.get('a')).toEqual({ x: 1, y: 2 })
    expect(positionsFromCache(cache, '2:a|b')).toBeNull()
  })
})
