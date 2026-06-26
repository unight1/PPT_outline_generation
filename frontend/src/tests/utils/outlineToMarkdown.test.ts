import { describe, it, expect } from 'vitest'
import { outlineToMarkdown } from '../../utils/outlineToMarkdown'
import type { Outline } from '../../types/task'

const basicOutline: Outline = {
  title: 'AI Education',
  slides: [
    {
      slide_id: 's1',
      title: 'Background',
      key_message: 'AI transforms education',
      bullets: [
        { bullet_id: 's1-b1', text: 'Market reaches 60B USD', evidence_ids: ['ev_1'] },
        { bullet_id: 's1-b2', text: 'Improves learning outcomes', evidence_ids: [] },
      ],
      speaker_notes: 'Start with market data',
      visual_suggestion: 'Bar chart',
      takeaway: 'Consider AI adoption',
    },
    {
      slide_id: 's2',
      title: 'Solution',
      bullets: [{ bullet_id: 's2-b1', text: 'RAG architecture', evidence_ids: [] }],
      speaker_notes: null,
    },
  ],
  evidence_catalog: [
    {
      evidence_id: 'ev_1',
      snippet: 'AI education market reaches 60 billion USD in 2024.',
      source_id: 'report.pdf',
      locator: 'L10',
      score: 0.9,
      confidence: 0.8,
    },
  ],
  meta: { retrieval_depth: 'L1', generated_at: '2025-01-01T00:00:00Z' },
}

describe('outlineToMarkdown', () => {
  it('includes title as H1', () => {
    const md = outlineToMarkdown(basicOutline)
    expect(md).toContain('# AI Education')
  })

  it('includes slide titles as H2', () => {
    const md = outlineToMarkdown(basicOutline)
    expect(md).toContain('## Background')
    expect(md).toContain('## Solution')
  })

  it('includes bullets with evidence references', () => {
    const md = outlineToMarkdown(basicOutline)
    expect(md).toContain('Market reaches 60B USD')
    expect(md).toContain('[ev_1]')
  })

  it('includes key_message, visual_suggestion, speaker_notes, takeaway', () => {
    const md = outlineToMarkdown(basicOutline)
    expect(md).toContain('AI transforms education')
    expect(md).toContain('Bar chart')
    expect(md).toContain('Start with market data')
    expect(md).toContain('Consider AI adoption')
  })

  it('includes evidence catalog', () => {
    const md = outlineToMarkdown(basicOutline)
    expect(md).toContain('## 证据目录')
    expect(md).toContain('report.pdf')
    expect(md).toContain('60 billion')
  })

  it('handles empty evidence catalog', () => {
    const outline: Outline = {
      ...basicOutline,
      evidence_catalog: [],
    }
    const md = outlineToMarkdown(outline)
    expect(md).not.toContain('## 证据目录')
  })

  it('handles empty speaker_notes gracefully', () => {
    const md = outlineToMarkdown(basicOutline)
    // Slide s2 has null speaker_notes — should not crash or inject "null"
    expect(md).not.toContain('null')
  })
})
