import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import GeneratingView from '../../components/GeneratingView.vue'
import type { Task } from '../../types/task'

const baseTask: Task = {
  task_id: 't-1',
  status: 'generating',
  created_at: '2025-01-01T00:00:00Z',
  updated_at: '2025-01-01T00:01:00Z',
  clarification: null,
  outline_skeleton: null,
  outline: null,
  progress: { phase: 'llm_page', current: 2, total: 5, message: 'Generating page 3…', percent: 40 },
  error: null,
}

const slides = [
  { slide_id: 's1', title: 'Page 1', index: 0, slide: null, status: 'done' as const },
  { slide_id: 's2', title: 'Page 2', index: 1, slide: null, status: 'done' as const },
  { slide_id: 's3', title: 'Page 3', index: 2, slide: null, status: 'generating' as const },
  { slide_id: 's4', title: 'Page 4', index: 3, slide: null, status: 'generating' as const },
  { slide_id: 's5', title: 'Page 5', index: 4, slide: { slide_id: 's5', title: 'Page 5', bullets: [{ bullet_id: 's5-b1', text: 'Test', evidence_ids: [] }], speaker_notes: null }, status: 'failed' as const },
]

function mountGen(overrides = {}) {
  return mount(GeneratingView, {
    props: { task: baseTask, slides, ...overrides },
    global: {
      stubs: { SlidePanel: { template: '<div class="slide-panel-stub" />' } },
    },
  })
}

describe('GeneratingView', () => {
  it('shows progress message', () => {
    const wrapper = mountGen()
    expect(wrapper.text()).toContain('Generating page 3…')
  })

  it('shows progress fill with width style', () => {
    const wrapper = mountGen()
    expect(wrapper.find('.progress-fill').exists()).toBe(true)
  })

  it('shows page status chips', () => {
    const wrapper = mountGen()
    const chips = wrapper.findAll('.status-chip')
    expect(chips.length).toBe(5)
  })

  it('shows done and generating chips', () => {
    const wrapper = mountGen()
    expect(wrapper.findAll('.status-chip.done').length).toBe(2)
    expect(wrapper.findAll('.status-chip.failed').length).toBe(1)
  })

  it('shows phase in summary', () => {
    const wrapper = mountGen()
    expect(wrapper.text()).toContain('llm_page')
  })

  it('clicking chip selects that slide', async () => {
    const wrapper = mountGen()
    const chips = wrapper.findAll('.status-chip')
    await chips[0].trigger('click')
    expect(chips[0].classes()).toContain('active')
  })
})
