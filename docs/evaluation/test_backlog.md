# Future Integration & Real API Connectivity Test Backlog

> **Objective**: The following test cases must be implemented when the system integrates with the actual DeepSeek-R1 interface and the live RAG retrieval stream.

## 1. Cross-Module Integration Testing
- **[A-B Linkage] Retrieval Depth Pass-through Test**:
    - Verify that when the frontend selects "L2" depth, Member A’s orchestration layer correctly passes `retrieval_depth=L2` to Member B’s retrieval module.
- **[A-C Linkage] Real-time Status Transition**:
    - Verify that when Member A’s task status transitions from `generating` to `done`, the frontend interface automatically refreshes to display the results within 2 seconds.

## 2. Robustness & Stress Testing
- **Extra-Long Text Handling**:
    - Input a 200-word topic description to test if Member B’s chunking logic handles the payload without crashing.
- **Concurrency Pressure**:
    - Initiate 5 outline generation tasks simultaneously to monitor server resource utilization and verify if Redis caching is functioning correctly.
- **API Timeout Fault Tolerance**:
    - Simulate an LLM interface response delay exceeding 60 seconds to verify that the system triggers the timeout error codes as defined in the `api_contract`.

## 3. RAG-Specific Factual Accuracy
- **Hallucination Detection**:
    - Provide a local document containing specific factual errors to observe whether the system "blindly follows" the misinformation or successfully filters it out via the Reranker.
- **Evidence Traceability**:
    - Randomly click 10 evidence tags generated on the frontend to verify if the corresponding `source_id` and `locator` accurately point to the original Markdown/PDF files.

## 4. Software Engineering Economics Metrics Audit
- **Token Consumption Statistics**:
    - Record the average Token count per outline generation to calculate the exact economic cost of a single request.