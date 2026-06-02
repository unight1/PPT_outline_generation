import type { Outline } from '../types/task'

export function outlineToMarkdown(outline: Outline): string {
  const lines: string[] = []
  lines.push(`# ${outline.title || '未命名大纲'}`)
  lines.push('')

  for (const slide of outline.slides) {
    lines.push('---')
    lines.push('')
    lines.push(`## ${slide.title || slide.slide_id}`)
    lines.push('')

    if (slide.key_message?.trim()) {
      lines.push(`**核心结论：** ${slide.key_message.trim()}`)
      lines.push('')
    }

    for (const bullet of slide.bullets) {
      const evidenceRefs =
        bullet.evidence_ids.length > 0
          ? ` \`[${bullet.evidence_ids.join(', ')}]\``
          : ''
      lines.push(`- ${bullet.text}${evidenceRefs}`)
    }
    lines.push('')

    if (slide.visual_suggestion?.trim()) {
      lines.push(`*配图建议：${slide.visual_suggestion.trim()}*`)
      lines.push('')
    }

    if (slide.speaker_notes) {
      const notes = slide.speaker_notes.replace(/\n/g, ' ')
      lines.push(`> 讲者备注：${notes}`)
      lines.push('')
    }

    if (slide.takeaway?.trim()) {
      lines.push(`**页级小结：** ${slide.takeaway.trim()}`)
      lines.push('')
    }
  }

  if (outline.evidence_catalog.length > 0) {
    lines.push('---')
    lines.push('')
    lines.push('## 证据目录')
    lines.push('')

    for (const ev of outline.evidence_catalog) {
      const scoreStr = ev.score != null ? ` score=${ev.score.toFixed(2)}` : ''
      const confStr = ev.confidence != null ? ` conf=${ev.confidence.toFixed(2)}` : ''
      lines.push(
        `- **[${ev.evidence_id}]** ${ev.snippet} — 来源：${ev.source_id}${scoreStr}${confStr}`,
      )
    }
    lines.push('')
  }

  return lines.join('\n')
}
