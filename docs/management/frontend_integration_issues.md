# Frontend Integration Issue List — Member C

## 1. Integration Scope

Frontend branch: `feature/frontend-mock-flow`

This checklist is used to record the frontend-backend integration status for the week 5–7 Member C tasks.

## 2. Main Flow Checklist

- [x] Frontend default mode uses the real backend API.
- [x] Mock API is kept as a fallback through `VITE_USE_MOCK_API=true`.
- [x] Requirement input form is connected to task creation.
- [x] Dynamic clarification questions are displayed from backend response.
- [x] Clarification answers can be submitted.
- [x] Outline generation can be triggered after clarification submission.
- [x] Frontend polls task status during generation.
- [x] Polling stops when task status becomes `done` or `failed`.
- [x] Outline result page displays slide title, bullet points, speaker notes, evidence references, and evidence catalog.

## 3. Error State Checklist

- [x] API request failure displays an error message.
- [x] Generation is blocked when clarification has not been submitted.
- [x] Failed task status displays error code and error message.
- [x] Polling timeout displays a timeout message.

## 4. Known Issues / To Be Confirmed

### Issue 1: Failed-task response format

Status: To be confirmed with backend.

Description: The frontend currently displays `task.error.code` and `task.error.message` when task status is `failed`. Need to confirm that the backend always returns these fields.

### Issue 2: Long-document input testing

Status: To be tested.

Description: The frontend supports long-document input, but more integration tests are needed to confirm the backend processing result.

### Issue 3: Evidence completeness

Status: To be checked during integration.

Description: The result page displays evidence references and evidence catalog. Need to confirm that every bullet evidence ID can be found in the evidence catalog.

## 5. Regression Record

- Test date:
- Tester: Member C
- Result: