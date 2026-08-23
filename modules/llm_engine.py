"""
llm_engine.py
The one external API call in the app: turning a rough, spoken transcript
("um, so I worked at, like, a coffee shop for two years, I basically ran
the register and trained new people...") into clean, structured résumé
text. Uses Google's Gemini API.

Kept isolated in this file on purpose — swap providers by editing only
this module.
"""

import json

from google import genai
from google.genai import types
import streamlit as st

MODEL = "gemini-2.5-flash"

_client = None


def _get_gemini_api_key() -> str | None:
    try:
        api_key = st.secrets.get("GEMINI_API_KEY")
    except (KeyError, FileNotFoundError):
        api_key = None
    return api_key.strip() if isinstance(api_key, str) and api_key.strip() else None


def get_client():
    global _client
    if _client is None:
        api_key = _get_gemini_api_key()
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY not set. Add it to Streamlit Secrets. Get a key from "
                "https://aistudio.google.com/apikey."
            )
        _client = genai.Client(api_key=api_key)
    return _client


def _call_json(prompt: str, max_tokens: int = 700) -> dict:
    client = get_client()
    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            max_output_tokens=max_tokens,
            response_mime_type="application/json",
        ),
    )
    if not response.text:
        raise ValueError("Gemini returned an empty response.")
    return json.loads(response.text.strip())


def structure_summary(transcript: str, target_role: str) -> str:
    prompt = f"""You are assisting with professional résumé preparation.
Rewrite the spoken notes below as a polished 2-3 sentence résumé summary for a
candidate targeting the "{target_role}" role. Keep only factual professional
information from the notes, remove filler and repetition, and do not infer
personal, sensitive, or unconfirmed details. Use concise third-person résumé
language.

Spoken notes begin:
---
{transcript}
---
Spoken notes end.

Respond ONLY with JSON: {{"summary": "..."}}"""
    return _call_json(prompt)["summary"]


def structure_experience(transcript: str) -> list[dict]:
    prompt = f"""You are assisting with professional résumé preparation.
Convert the spoken work-history notes below into structured résumé entries.
Extract job title, company, and approximate duration only when stated. Create
2-4 concise accomplishment bullets per role using strong action verbs. Preserve
the speaker's facts, and never invent achievements, numbers, qualifications,
or personal details.

Work-history notes begin:
---
{transcript}
---
Work-history notes end.

Respond ONLY with JSON: {{"experience": [{{"title": "...", "company": "...",
"duration": "...", "bullets": ["...", "..."]}}]}}"""
    return _call_json(prompt, max_tokens=900)["experience"]


def structure_education(transcript: str) -> list[dict]:
    prompt = f"""You are assisting with professional résumé preparation.
Convert the education notes below into structured résumé entries. Include a
degree, institution, and year only when explicitly provided. Do not guess or
add personal or sensitive information.

Education notes begin:
---
{transcript}
---
Education notes end.

Respond ONLY with JSON: {{"education": [{{"degree": "...", "institution": "...",
"year": "..."}}]}}"""
    return _call_json(prompt)["education"]


def structure_skills(transcript: str) -> list[str]:
    prompt = f"""You are assisting with professional résumé preparation.
Extract a deduplicated list of concrete professional skills explicitly stated
in the notes below, including tools, languages, frameworks, and relevant
strengths. Do not infer skills that are not stated.

Skills notes begin:
---
{transcript}
---
Skills notes end.

Respond ONLY with JSON: {{"skills": ["...", "..."]}}"""
    return _call_json(prompt)["skills"]


def generate_confirmation_summary(resume: dict) -> str:
    """A short spoken-style readback of the finished résumé, for TTS."""
    prompt = f"""Here is a finished résumé in JSON:
{json.dumps(resume, indent=2)}

Write a short, warm, spoken-style summary (4-5 sentences) confirming what
was captured — mention their target role, how many roles/education entries
were captured, and one standout bullet point. Plain text only, ready to be
read aloud by a text-to-speech engine, no markdown.Also mention, what can be changed and added to be better into the resume. 

Respond ONLY with JSON: {{"summary": "..."}}"""
    return _call_json(prompt)["summary"]
