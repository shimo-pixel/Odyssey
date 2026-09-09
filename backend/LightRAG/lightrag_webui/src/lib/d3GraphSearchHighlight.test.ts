import { describe, expect, test } from 'bun:test'
import { resolveGraphSearchHighlight } from '@/lib/d3GraphSearchHighlight'

describe('resolveGraphSearchHighlight', () => {
  const graphData = {
    nodes: [
      { id: 'Pilot A', labels: ['Pilot A'], properties: { entity_id: 'Pilot A' } },
      { id: 'Unit X', labels: ['Unit X'], properties: { entity_id: 'Unit X' } },
      { id: 'Other', labels: ['Other'], properties: { entity_id: 'Other' } }
    ],
    edges: [
      {
        id: 'e1',
        source: 'Pilot A',
        target: 'Unit X',
        type: 'DIRECTED',
        properties: {}
      },
      {
        id: 'e2',
        source: 'Other',
        target: 'Unit X',
        type: 'DIRECTED',
        properties: {}
      }
    ]
  }

  test('maps entity names and relationship pairs to graph ids', () => {
    const result = resolveGraphSearchHighlight(graphData, {
      entityNames: ['Pilot A', 'Unit X'],
      relationships: [{ source: 'Pilot A', target: 'Unit X' }],
      focusEntityNames: ['Pilot A']
    })

    expect(result.nodeIds.sort()).toEqual(['Pilot A', 'Unit X'])
    expect(result.edgeIds).toEqual([])
    expect(result.focusNodeIds).toEqual(['Pilot A'])
  })
})
