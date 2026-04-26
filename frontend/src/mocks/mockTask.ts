import type { Task } from '../types/task'

export const mockTaskClarifying: Task = {
  task_id: '550e8400-e29b-41d4-a716-446655440000',
  status: 'clarifying',
  created_at: '2026-04-15T10:00:00+08:00',
  updated_at: '2026-04-15T10:05:00+08:00',
  clarification: {
    submitted: false,
    questions: [
      {
        question_id: 'goal',
        prompt: '本次演示希望听众记住的一个核心结论是什么？',
        answer: null,
      },
      {
        question_id: 'audience_level',
        prompt: '听众对这个主题的熟悉程度如何？',
        answer: null,
      },
      {
        question_id: 'style',
        prompt: '希望 PPT 风格更偏正式汇报、课堂展示，还是商业路演？',
        answer: null,
      },
    ],
  },
  outline: null,
  error: null,
}

export const mockTaskDone: Task = {
  task_id: '550e8400-e29b-41d4-a716-446655440000',
  status: 'done',
  created_at: '2026-04-15T10:00:00+08:00',
  updated_at: '2026-04-15T10:10:00+08:00',
  clarification: {
    submitted: true,
    questions: [
      {
        question_id: 'goal',
        prompt: '本次演示希望听众记住的一个核心结论是什么？',
        answer: 'AI 可以显著提升 PPT 大纲生成效率，但需要证据支撑和人工校对。',
      },
      {
        question_id: 'audience_level',
        prompt: '听众对这个主题的熟悉程度如何？',
        answer: '听众是普通本科生，了解一点 AI，但不了解 RAG。',
      },
      {
        question_id: 'style',
        prompt: '希望 PPT 风格更偏正式汇报、课堂展示，还是商业路演？',
        answer: '课堂展示。',
      },
    ],
  },
  outline: {
    title: '基于 RAG 的 PPT 大纲智能生成系统',
    slides: [
      {
        slide_id: 's1',
        title: '项目背景',
        bullets: [
          {
            bullet_id: 's1-b1',
            text: '传统 PPT 大纲撰写耗时，且容易缺少资料依据。',
            evidence_ids: ['ev_1'],
          },
          {
            bullet_id: 's1-b2',
            text: '生成式 AI 可以帮助用户快速形成初稿。',
            evidence_ids: ['ev_2'],
          },
        ],
        speaker_notes: '这一页主要说明为什么要做这个系统。',
      },
      {
        slide_id: 's2',
        title: '系统目标',
        bullets: [
          {
            bullet_id: 's2-b1',
            text: '根据用户主题、听众、时长等信息生成结构化 PPT 大纲。',
            evidence_ids: [],
          },
          {
            bullet_id: 's2-b2',
            text: '通过证据目录展示每个要点背后的资料来源。',
            evidence_ids: ['ev_3'],
          },
        ],
        speaker_notes: '强调系统不仅生成文字，还要尽量可追溯。',
      },
      {
        slide_id: 's3',
        title: '核心流程',
        bullets: [
          {
            bullet_id: 's3-b1',
            text: '前端收集需求，后端创建任务并进入澄清流程。',
            evidence_ids: [],
          },
          {
            bullet_id: 's3-b2',
            text: '检索模块返回证据片段，生成模块组织成大纲。',
            evidence_ids: ['ev_3'],
          },
        ],
        speaker_notes: '这里可以配一张流程图，后续版本再补。',
      },
    ],
    evidence_catalog: [
      {
        evidence_id: 'ev_1',
        snippet: '用户在制作演示文稿时，通常需要先整理主题、结构和材料。',
        source_id: 'sample_doc_intro',
        locator: 'L12-L18',
        score: 0.82,
        confidence: 0.71,
      },
      {
        evidence_id: 'ev_2',
        snippet: '大语言模型适合用于生成初稿、改写、摘要和结构化内容。',
        source_id: 'sample_doc_llm',
        locator: 'L20-L26',
        score: 0.78,
        confidence: 0.69,
      },
      {
        evidence_id: 'ev_3',
        snippet: 'RAG 可以把检索到的资料片段作为生成内容的依据。',
        source_id: 'sample_doc_rag',
        locator: 'L30-L35',
        score: 0.88,
        confidence: 0.77,
      },
    ],
    meta: {
      retrieval_depth: 'L1',
      generated_at: '2026-04-15T10:10:00+08:00',
    },
  },
  error: null,
}