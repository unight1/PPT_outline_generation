# Cost of Quality (CoQ) Analysis Report - April 2026

## 1. Prevention Costs
- **API Contract Specification**: By defining `TaskStatus` and data structures early, we reduced communication redundancy during the WBS 3.2 integration phase, resulting in an estimated **15% saving** in joint debugging man-hours.
- **Environment Standardization**: Utilizing Docker (`docker-compose.yml`) to unify MySQL/Redis environments eliminated the troubleshooting costs associated with the "it works on my machine" syndrome.

## 2. Appraisal Costs
- **Automated Testing Investment**: Member B developed **38 Pytest cases**.
- **Scope of Coverage**: The tests cover core components including Embedding, ChromaDB indexing, and Reranker logic.

## 3. Failure Costs - Risk Case Study
- **Case**: ChromaDB Index Persistence Bug.
- **Analysis**: Had this bug surfaced during the WBS 0.2 (Project Demonstration) phase, the cost of repair would have been **more than 10 times higher** than in the development phase. By investing in Appraisal Costs (writing tests), we successfully mitigated this significant Failure Cost.