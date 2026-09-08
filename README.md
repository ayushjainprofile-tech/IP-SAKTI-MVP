# IP-SAKTI MVP

A beginner-friendly prototype for an evidence-first IP / Traditional Knowledge / ABS assessment workflow.

## What this MVP demonstrates

User → Product Intake → Guided Classification → Jurisdiction → Domain Router → Hybrid Retrieval → Evidence Ranking → Reasoning → Claim Validation → Verified/Abstain → Confidence → Action Plan.

### Important
This is a hackathon prototype, not legal advice. It does not determine legal rights or guarantee patentability.

## Stack

- Frontend: React + Vite
- Backend: FastAPI
- Retrieval: scikit-learn TF-IDF + keyword matching ("hybrid" retrieval)
- Database: SQLite for zero-configuration local development
- Optional LLM: OpenAI-compatible reasoning is intentionally left as an optional extension; the MVP works without an API key.

## 1. Requirements

Install:
- Node.js 18+
- Python 3.10+

## 2. Run backend

```bash
cd backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate

pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Backend: http://localhost:8000
Swagger docs: http://localhost:8000/docs

## 3. Run frontend

Open another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open the URL Vite prints, usually http://localhost:5173.

## 4. Demo

Use:

Product: Ashwa Joint Relief
Ingredients: Ashwagandha, Turmeric
Purpose: Joint pain
Type: Ayurvedic formulation
Jurisdiction: India

Click Analyze.

The backend will:
1. classify the product;
2. route it to IP/TK/ABS;
3. retrieve evidence from `backend/data/corpus.json`;
4. rank the evidence;
5. create a demo reasoning result;
6. validate claims against retrieved evidence;
7. return VERIFIED or ABSTAIN;
8. calculate an evidence confidence score;
9. create an action plan.

## 5. Adding real sources

Do NOT blindly scrape or redistribute restricted databases.

Instead, collect only material you are permitted to use from authoritative public sources and preserve source metadata.

The starter corpus contains illustrative records so the app works immediately.

Recommended source categories:
- TKDL: https://www.tkdl.res.in/
- India Code: https://www.indiacode.nic.in/
- IP India: https://ipindia.gov.in/
- National Biodiversity Authority: https://nbaindia.org/

Each corpus record should contain:
- id
- title
- source
- source_url
- domain
- jurisdiction
- document_type
- text

## 6. Production upgrades

After the MVP works:
- replace SQLite with PostgreSQL + pgvector;
- add real document ingestion/PDF extraction;
- use dense embeddings alongside lexical search;
- add reranking;
- add an LLM with structured JSON output;
- implement stronger claim-to-evidence entailment;
- add authentication/audit logs;
- add human-review workflow;
- add source freshness/version tracking.

## Project structure

```text
ip-sakti-mvp/
├── backend/
│   ├── data/
│   │   └── corpus.json
│   ├── main.py
│   ├── rag.py
│   ├── models.py
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── main.jsx
│   │   └── index.css
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
└── README.md
```
