import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import SlidePanel from '../../components/SlidePanel.vue'
import type { Slide, Evidence } from '../../types/task'

const baseSlide: Slide = {
  slide_id: 's1',
  title: 'Background',
  key_message: 'AI transforms education',
  bullets: [
    { bullet_id: 's1-b1', text: 'Market reaches 60B', evidence_ids: ['ev_1'] },
    { bullet_id: 's1-b2', text: 'Improves outcomes', evidence_ids: [] },
  ],
  speaker_notes: 'Start with data',
  visual_suggestion: 'Bar chart',
  takeaway: 'Adopt AI',
}

const evidence: Evidence[] = [
  { evidence_id: 'ev_1', snippet: 'AI market 60 billion USD', source_id: 'report.pdf', locator: 'L10', score: 0.9, confidence: 0.8 },
]

function mountSlide(overrides = {}) {
  return mount(SlidePanel, {
    props: {
      slide: baseSlide,
      index: 0,
      total: 6,
      editable: true,
      regenerating: false,
      evidenceCatalog: evidence,
      ...overrides,
    },
    global: {
      stubs: {
        'n-modal': {
          template: '<div v-if="show"><slot /></div>',
          props: ['show'],
          emits: ['update:show'],
        },
      },
    },
  })
}

describe('SlidePanel', () => {
  it('displays page badge with index/total', () => {
    const wrapper = mountSlide()
    expect(wrapper.text()).toContain('1 / 6')
  })

  it('displays slide title as input when editable', () => {
    const wrapper = mountSlide({ editable: true })
    expect(wrapper.find('input.title-inline').exists()).toBe(true)
  })

  it('displays slide title as strong when not editable', () => {
    const wrapper = mountSlide({ editable: false })
    expect(wrapper.find('.page-title-label').exists()).toBe(true)
  })

  it('shows evidence button when bullet has evidence_ids', () => {
    const wrapper = mountSlide()
    expect(wrapper.text()).toContain('证据详情')
  })

  it('hides regenerate button when not editable', () => {
    const wrapper = mountSlide({ editable: false })
    expect(wrapper.text()).not.toContain('重新生成')
  })

  it('does not show evidence button without evidence', () => {
    const wrapper = mountSlide({ evidenceCatalog: [] })
    expect(wrapper.text()).not.toContain('证据详情')
  })

  it('renders key_message, visual_suggestion, takeaway fields', () => {
    const wrapper = mountSlide({ editable: false })
    expect(wrapper.text()).toContain('AI transforms education')
    expect(wrapper.text()).toContain('Bar chart')
    expect(wrapper.text()).toContain('Adopt AI')
  })
})
