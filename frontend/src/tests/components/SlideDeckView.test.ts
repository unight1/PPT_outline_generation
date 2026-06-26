import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import SlideDeckView from '../../components/SlideDeckView.vue'
import type { Outline } from '../../types/task'

const outline: Outline = {
  title: 'Test Outline',
  slides: [
    { slide_id: 's1', title: 'Page One', bullets: [{ bullet_id: 's1-b1', text: 'A', evidence_ids: [] }], speaker_notes: null },
    { slide_id: 's2', title: 'Page Two', bullets: [{ bullet_id: 's2-b1', text: 'B', evidence_ids: [] }], speaker_notes: null },
    { slide_id: 's3', title: 'Page Three', bullets: [{ bullet_id: 's3-b1', text: 'C', evidence_ids: [] }], speaker_notes: null },
  ],
  evidence_catalog: [],
  meta: {},
}

function mountDeck(overrides = {}) {
  return mount(SlideDeckView, {
    props: {
      outline,
      taskProgress: null,
      regeneratingSlideId: null,
      saving: false,
      saveMessage: '',
      ...overrides,
    },
    global: {
      stubs: {
        SlidePanel: { template: '<div class="slide-panel-stub"><slot /></div>' },
      },
    },
  })
}

describe('SlideDeckView', () => {
  it('displays page list with slide titles', () => {
    const wrapper = mountDeck()
    expect(wrapper.text()).toContain('Page One')
    expect(wrapper.text()).toContain('Page Two')
    expect(wrapper.text()).toContain('3 页')
  })

  it('shows first page initially', () => {
    const wrapper = mountDeck()
    expect(wrapper.text()).toContain('1 / 3')
  })

  it('prev button is disabled on first page', () => {
    const wrapper = mountDeck()
    const buttons = wrapper.findAll('button')
    const prevBtn = buttons.find(b => b.text().includes('上一页'))
    expect(prevBtn?.element.hasAttribute('disabled')).toBe(true)
  })

  it('clicking page thumb changes current slide', async () => {
    const wrapper = mountDeck()
    const thumbs = wrapper.findAll('.page-thumb')
    await thumbs[1].trigger('click')
    expect(wrapper.text()).toContain('2 / 3')
  })
})
