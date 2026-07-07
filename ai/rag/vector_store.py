"""
ai/rag/vector_store.py

Rewritten RAG agent.

Key change from the original: condition_engine.py already tells us EXACTLY
which condition matched (by id, e.g. "EYE001") — so instead of re-guessing
via a fake keyword-count loop over collection.get(), we fetch that document
directly by id. The LLM's only job is to phrase the retrieved KB content
nicely; it never invents medical facts outside the curated document.

If no LLM API key is configured (CLARIMED_LLM_KEY unset) — which is the
default, offline-first case — this falls back to a clean, structured
summary built directly from the document's own sections. The app is fully
functional with zero internet access; the LLM is a phrasing upgrade, not
a requirement.
"""

import os
import chromadb
from openai import OpenAI

from ai.rag.kb_loader import _split_sections

COLLECTION_NAME = "clarimed_kb"

SYSTEM_INSTRUCTIONS = (
    "You are ClariMed AI, an automated assistant for PRELIMINARY SYMPTOM SCREENING.\n"
    "CRITICAL: You are an AI, NOT a medical doctor. You CANNOT diagnose conditions or prescribe medications.\n"
    "You must base your answer ONLY on the Context Document provided below — do not add medical facts "
    "that are not present in it.\n\n"
    "Output your breakdown using exactly these markdown headers:\n"
    "### Preliminary Screening Insights\n"
    "### Context-Aware Explanation\n"
    "### Recommended Home Care & Precautions\n"
    "### Clinical Escalation Triggers\n"
    "Explicitly state this is an exploratory screening tool, not a diagnosis."
)


class ClariMedRAGAgent:
    def __init__(self):
        self.chroma_client = chromadb.PersistentClient(path="./chroma_db")
        self.collection = self.chroma_client.get_collection(name=COLLECTION_NAME)

        self.llm_key = os.getenv("CLARIMED_LLM_KEY", "")
        self.llm_client = None
        if self.llm_key:
            self.llm_client = OpenAI(api_key=self.llm_key, base_url="https://api.groq.com/openai/v1")

    def _fetch_by_id(self, disease_id: str):
        res = self.collection.get(ids=[disease_id])
        docs = res.get("documents") or []
        metas = res.get("metadatas") or []
        if not docs:
            return None, None
        return docs[0], (metas[0] if metas else {})

    def process_screening(self, selected_symptoms, voice_transcript, disease_id: str = None) -> str:
        if not disease_id:
            return "No matched condition was provided to the guidance engine."

        doc_text, meta = self._fetch_by_id(disease_id)
        if doc_text is None:
            return f"⚠️ Knowledge base entry '{disease_id}' not found. Try rerunning `python -m ai.rag.kb_initializer`."

        disease_name = meta.get("disease_name", disease_id)

        # --- Try LLM phrasing if a key is configured ---
        if self.llm_client:
            user_prompt = (
                f"Context Document ({disease_name}):\n{doc_text}\n\n"
                f"Patient's selected symptoms: {selected_symptoms}\n"
                f"Additional patient notes: {voice_transcript or 'None'}"
            )
            try:
                response = self.llm_client.chat.completions.create(
                    model="llama3-8b-8192",
                    messages=[
                        {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.2,
                )
                return response.choices[0].message.content
            except Exception as e:
                # Fall through to the offline structured summary below
                pass

        # --- Offline-safe structured fallback (no internet / no API key needed) ---
        return self._structured_fallback(doc_text, disease_name, selected_symptoms)

    @staticmethod
    def _structured_fallback(doc_text: str, disease_name: str, selected_symptoms) -> str:
        sections = _split_sections(doc_text.replace("\r\n", "\n"))
        overview = sections.get("Overview", "").strip()
        home_care = sections.get("Home Care", "").strip()
        prevention = sections.get("Prevention", "").strip()
        when_to_consult = sections.get("When to Consult a Doctor", "").strip()
        emergency = sections.get("Emergency Warning Signs", "").strip()

        parts = [
            "### Preliminary Screening Insights",
            f"Possible condition (preliminary, unconfirmed): **{disease_name}**",
            f"Reported symptoms considered: {', '.join(selected_symptoms) if selected_symptoms else 'None specified'}",
            "",
            "### Context-Aware Explanation",
            overview or "No overview available.",
            "",
            "### Recommended Home Care & Precautions",
            home_care or "See a healthcare professional for guidance.",
            prevention,
            "",
            "### Clinical Escalation Triggers",
            when_to_consult or "Consult a doctor if symptoms persist or worsen.",
            emergency,
            "",
            "*This response was generated from ClariMed's curated knowledge base "
            "(offline mode — no LLM API key configured or LLM unavailable). "
            "This is an exploratory screening tool, not a diagnosis.*",
        ]
        return "\n".join(p for p in parts if p is not None)


if __name__ == "__main__":
    agent = ClariMedRAGAgent()
    print("LLM configured:", bool(agent.llm_client))
    out = agent.process_screening(["Ocular Redness", "Watery Eyes"], "", disease_id="EYE001")
    print(out)