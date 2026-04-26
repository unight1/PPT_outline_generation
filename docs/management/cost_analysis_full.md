# Project Economics Analysis: Cost Estimation Based on COCOMO II

## 1. Software Sizing
Based on the two-week output of Member B (1.1 KLOC), the total project scale is estimated as follows:
* **Member A (Orchestration):** Estimated 1.5 KLOC (Complex logic, medium code volume)
* **Member B (Retrieval):** 1.1 KLOC (Delivered)
* **Member C (Frontend):** 2.0 KLOC (High volume of UI interaction code)
* **Member D (Testing/Doc):** 0.5 KLOC (Scripts and configuration files)
* **Total Scale:** ~5.1 KLOC

## 2. Effort Calculation
Using the COCOMO II Early Design Model:
* **Effort (Person-Months)** = $A \times (Size)^E \times \prod(EM)$
* Considering the skill level of team members as university students (**Low Experience**), the Effort Multiplier (EM) is adjusted to **1.15**.
* **Estimated Result:** Total effort invested for this sprint is approximately **3.2 Person-Months**.



## 3. Economic Value of Task Distribution
* **Module A:** Reduced group-wide integration risks through the design of standardized **API Contracts**.
* **Module B:** Implemented **L0/L1/L2 Depth Tiering**, achieving optimal marginal utility between computational resources and factual accuracy.
* **Module C:** Decreased the **Learning Cost** for end-users through intuitive interface design.
* **Module D:** Minimized the project's **Failure Cost** by implementing 38 automated test cases.