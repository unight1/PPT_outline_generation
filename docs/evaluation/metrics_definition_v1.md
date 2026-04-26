# System Evaluation Metrics Specification (v1.0)

## 1. Quality Metrics
- **Factual Accuracy**:
    - **Definition**: The proportion of generated outline bullet points that are supported by verifiable evidence.
    - **Calculation**: `(Number of bullets supported by an evidence_id) / (Total number of bullets)`.
    - **Acceptance Threshold**: ≥ 90% [Based on RBS.png].
- **Evidence Reliability**:
    - **Definition**: The proportion of sources within the `evidence_catalog` that originate from verified or trusted repositories.

## 2. Performance Metrics
- **Generation Latency**:
    - **Definition**: The total elapsed time from when the task status changes to `generating` until it reaches `done`.
    - **Target**: Average of ≤ 20 minutes per individual task [Based on RBS.png].
- **Retrieval Response Time**: Evaluating the latency variance across Member B’s retrieval module for different depth levels (L0/L1/L2).

## 3. Compliance
- **API Consistency**: The degree of alignment between the backend response fields and the definitions in `api_contract_v0.md`.