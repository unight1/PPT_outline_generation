# Weeks 10 Biweekly Report — FE-1 (Frontend Main Flow + UI Overhaul)

## Completed Work

### FE-1a · Global Navigation & Layout

Redesigned the entire application shell from scratch:
- Replaced the verbose hero + step bar (~150px waste) with a compact 48px top bar containing the app name, a 4-step indicator (`n-steps`), and an API mode tag.
- Introduced a **fixed bottom bar** (56px) that holds all action buttons relevant to the current step — users no longer need to scroll to find controls. Button labels and types adapt dynamically: "Next: Answer Questions" on the form, "Submit Clarification" on the status page, "Generate Pages" on the skeleton editor, "Save Changes" / "Copy Markdown" / "Download .md" on the result view.
- The content area between header and footer takes the remaining viewport height and scrolls independently, eliminating page-level scrolling.

### FE-1b · Create Task Page

- Partitioned the form into logical sections: Topic & Scenario / Material Type / Advanced Options (collapsible).
- Replaced raw `<select>` / `<input>` elements with `n-select`, `n-input`, `n-input-number` components for consistent styling and better UX.
- Retrieval depth labels rewritten in plain language: "资料少查" (L0) / "平衡" (L1) / "多查引用" (L2).
- Long document mode: added character count feedback and a dedicated document text area.
- Primary button reads "下一步：回答问题" (Next: Answer Questions) to guide the user flow.

### FE-1c · Clarification Page

- Made the clarification page an independent view (`view = 'status'`), no longer mixed with generation progress or failure messages.
- Each question renders as a `<n-input>` textarea with the pre-filled answer clearly visible.
- After submission, a single path leads to the skeleton editor — duplicate action buttons removed.

### FE-1d · Skeleton Editor

- Skeleton slides displayed in a 2-column `<n-grid>` with embedded `n-card` components. Each card shows the slide title, intent, and user notes in compact `n-input` fields.
- Generation parameters (depth, concurrency, Tavily toggle, force refresh) moved into a collapsible "高级选项" (Advanced Options) section.
- Action buttons in the footer: "Save Skeleton", "+ Add Page", and "Generate Pages".

### UI Component Library Integration

Introduced **Naive UI** (`naive-ui`) as the design system for the entire frontend:
- All form elements (`n-input`, `n-select`, `n-checkbox`, `n-input-number`, `n-textarea`) provide consistent sizing, focus states, and validation feedback.
- Layout uses a custom flexbox shell (`app-shell` → `app-topbar` + `app-body` + `app-bottombar`) with `100vh` height — the header and footer are fixed, the body scrolls independently.
- Progress indicators use `n-progress`; the generation dialog uses `n-modal` with a card preset.
- Step indicator uses `n-steps` with the `process` / `finish` status reflecting actual task completion.

### Result View Polishing

- Evidence catalog moved from a page-level list to a **per-slide modal dialog** (`n-modal`): clicking "证据详情 · N 条" opens a card with full evidence details for that slide, freeing vertical space.
- Removed duplicate page title display — the title now appears only in the slide header, with inline editing when editable.
- Page navigation (`← 上一页` / `下一页 →`) and the regenerate button are `position: sticky` so they remain visible while the editing area scrolls.
- Scrollbar spacing (`padding-right: 12px`) prevents overlap with edit fields.

---

## Key Files Changed

| File | Changes |
|------|---------|
| `frontend/src/App.vue` | Complete rewrite: Naive UI imports, flexbox layout shell, 4-step n-steps, fixed footer with dynamic buttons, n-card per view, ~840 lines (down from 1224) |
| `frontend/src/components/SlidePanel.vue` | Single-slide editing with inline title, collapsible two-col layout, evidence modal, sticky header |
| `frontend/src/components/SlideDeckView.vue` | Left sidebar page list + main panel with sticky nav and internal scroll |
| `frontend/src/components/GeneratingView.vue` | Generation progress in n-modal dialog with page status chips |
| `frontend/src/components/TaskSidebar.vue` | Placeholder for task history and advanced search options |
| `frontend/package.json` | Added `naive-ui` dependency |

---

## Next Steps

- **C1–C8 integration**: connect the placeholder shells (task history, document analysis status, upload) to real API endpoints once the backend counterparts (BE-1, BE-2) are ready.
- **Skeleton left-right split**: implement the dual-pane skeleton editor (outline on left, preview on right) as described in A6.
- **Accessibility pass**: add keyboard navigation for the step indicator and slide deck.
- **Performance**: lazy-load the generating modal and slide components to reduce initial bundle size.
