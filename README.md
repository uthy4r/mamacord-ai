# 🤱 Mamacord AI
### *Connecting 30% of the World's Maternal Deaths to the Care That Can Stop Them.*

Mamacord AI is an AI-powered maternal triage and referral coordination tool designed for frontline health workers (Traditional Birth Attendants, Community Health Workers, and PHC nurses) operating in low-resource Nigerian settings without access to specialist care or electronic health records.

Given a set of structured clinical inputs, Mamacord AI returns an evidence-based **Green / Yellow / Red** risk classification grounded in the Nigerian National Maternal Health Guidelines and WHO Pregnancy Protocols, and automatically generates a structured clinical handover note for Red-flag cases.

---

## 🩺 The Problem

Nigeria accounts for nearly **30% of all global maternal deaths**: 1,047 per 100,000 live births. The three leading causes (pre-eclampsia, obstetric haemorrhage, and sepsis) are all detectable with basic clinical assessment.

The gap is not medical knowledge. **It is the absence of objective triage tools at the point of first contact.**

---

## ✅ What Mamacord AI Does

- Accepts structured manual input of patient vitals, point-of-care lab results, and USS findings
- Runs a RAG pipeline grounded in WHO and Nigerian national maternal health guidelines
- Returns a **Green / Yellow / Red** risk classification with cited clinical rationale
- Automatically generates a structured referral handover note for Red-flag cases
- Delivers targeted health literacy content to frontline workers and patients

---

## 🏗️ Architecture

```
🔢 Structured Clinical Inputs (vitals, labs, USS findings)
    ↓
⚙️  FastAPI Backend
    ↓
🔍 Hybrid Retrieval: ChromaDB (semantic) + BM25 Re-ranking
    ↓
📚 Evidence Retrieval: WHO & Nigerian National Maternal Health Guidelines
    ↓
✍️  Evidence-Grounded Prompt Construction
    ↓
🤖 GPT-4o-mini: Risk Classification + Clinical Rationale
    ↓
🟢🟡🔴 Triage Output + Auto-generated Referral Handover Note
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React (Vite), Tailwind CSS, Lucide-React |
| Backend | FastAPI (Python) |
| LLM | GPT-4o-mini (OpenAI) |
| Vector DB | ChromaDB (local persistent client) |
| Embeddings | text-embedding-3-small |
| Search | Hybrid: ChromaDB semantic + BM25 re-ranking |

---

## 🎯 Clinical Scope

Mamacord AI triages for the **Big Three** obstetric killers:

- 🩸 **Obstetric haemorrhage**
- 💉 **Hypertensive disorders** (pre-eclampsia / eclampsia)
- 🌡️ **Sepsis in pregnancy**

**Input parameters:** blood pressure, temperature, maternal heart rate, haemoglobin, urine protein, urine glucose, and USS findings (placental location, fetal presentation, liquor volume, fetal heart rate).

---

## 🛡️ Safety & Hallucination Control

- 🚫 Refuses to generate a triage classification if retrieved evidence is insufficient or incomplete
- ✅ All outputs grounded in WHO and Nigerian National Maternal Health Guidelines; no unsupported generation
- 📋 Auto-generates a structured clinical handover note for every Red-flag case
- 🔁 Includes escalation pathways connecting frontline workers to higher-level facility care

---

## 🚀 Getting Started

```bash
# 1. Clone the repository
git clone https://github.com/uthy4r/mamacord-ai.git
cd mamacord-ai

# 2. Backend setup
cd backend
pip install fastapi uvicorn openai chromadb python-dotenv rank-bm25
echo "OPENAI_API_KEY=your_key_here" > .env
python ingest.py        # Seeds the local WHO knowledge base
uvicorn main:app --reload

# 3. Frontend setup
cd ../frontend
npm install
npm run dev             # Opens at http://localhost:5173
```

---

## 👥 Team

**Mamacord AI · SRHIN Alpha Team 2026**  
Built at the **Harvard Health Systems Innovation Lab (HSIL) Hackathon 2026** — *Building High-Value Health Systems Through AI.*

| Name | Role |
|---|---|
| Dr. Uthman Babatunde | Clinical Lead · Medical Doctor / AI Researcher |
| Olamide Oso | AI Software Engineer |
| Fadekemi Fadare | Public Health Expert |
| Ezekiel Oladejo | Business Expert |

---

## 📚 Clinical References

- Federal Ministry of Health Nigeria. *National Maternal Health Policy and Guidelines.*
- WHO. (2023). *WHO Recommendations on Maternal Health.*
- WHO. (2021). *Managing Complications in Pregnancy and Childbirth.*

---

## 📁 Repository Structure

```
mamacord-ai/
├── backend/
│   ├── main.py              # FastAPI application
│   ├── ingest.py            # Knowledge base seeding pipeline
│   ├── rag_pipeline.py      # Hybrid retrieval + generation logic
│   └── .env.example         # Environment variables template
├── frontend/
│   ├── src/
│   │   ├── components/      # React UI components
│   │   └── App.jsx          # Main application entry
│   └── index.html
├── data/
│   └── guidelines/          # WHO & Nigerian MH guideline chunks
├── .gitignore
├── requirements.txt
└── README.md
```

---

## 🌐 Deployment Status

| Component | Status |
|---|---|
| Frontend | ✅ React (Vite) · Local |
| Backend | ✅ FastAPI · Local |
| Vector DB | ✅ ChromaDB · Local persistent |
| LLM | ✅ OpenAI GPT-4o-mini · Cloud |

> Cloud deployment in progress.

---

## ⚠️ Disclaimer

Mamacord AI is a clinical decision support tool. It does not replace the judgement of a qualified medical professional. All triage outputs must be interpreted in the context of the full clinical picture by a trained health worker.

---

*Mamacord AI · Harvard HSIL Hackathon 2026 · Nigeria*
