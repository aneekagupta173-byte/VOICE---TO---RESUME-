"""
roast_engine.py
The "Roast My Résumé" feature: extracts plain text from an uploaded résumé
(.docx, .pdf, or .txt) or from a résumé this app just built, then asks the
LLM for a funny-but-genuinely-useful critique — not just jokes, each roast
line is paired with a real, actionable fix.

The response is requested in Gemini's JSON mode and normalized before it is
passed to the UI, so the app always receives one predictable shape.
"""

import io
import json
import re
from typing import Any

from docx import Document
from google.genai import types
from pypdf import PdfReader
import streamlit as st

from modules.llm_engine import get_client, log_token_usage, MODEL


def extract_text_from_upload(uploaded_file) -> str:
    """uploaded_file is a Streamlit UploadedFile (has .name and .getvalue())."""
    name = uploaded_file.name.lower()
    data = uploaded_file.getvalue()

    if name.endswith(".docx"):
        doc = Document(io.BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())

    if name.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    if name.endswith(".txt"):
        return data.decode("utf-8", errors="ignore")

    raise ValueError("Unsupported file type — please upload a .docx, .pdf, or .txt résumé.")


def resume_dict_to_text(resume: dict) -> str:
    """Flattens a résumé this app just built into plain text for roasting."""
    lines = [resume.get("name", ""), resume.get("summary", "")]
    for job in resume.get("experience", []):
        lines.append(f"{job.get('title', '')} at {job.get('company', '')} "
                      f"({job.get('duration', '')})")
        lines.extend(f"- {b}" for b in job.get("bullets", []))
    for edu in resume.get("education", []):
        lines.append(f"{edu.get('degree', '')}, {edu.get('institution', '')} "
                      f"({edu.get('year', '')})")
    if resume.get("skills"):
        lines.append("Skills: " + ", ".join(resume["skills"]))
    return "\n".join(l for l in lines if l)


def _clean_text(text: str) -> str:
    """Fixes common PDF ligature artifacts (fi, fl, etc.) and extra blank lines."""
    replacements = {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl"}
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    return re.sub(r"\n{2,}", "\n", text).strip()


def _extract_json_object(raw: str) -> dict:
    """
    Pulls a JSON object out of a raw LLM response even if there's extra text
    around it. Prefers content after a ```json fence (the model's later,
    cleaner attempt) when one is present, then scans for the first balanced
    {...} block and parses it.
    """
    raw = raw.strip().replace("```json", "").replace("```", "").strip()
    decoder = json.JSONDecoder()

    for start, character in enumerate(raw):
        if character != "{":
            continue
        try:
            data, _ = decoder.raw_decode(raw[start:])
        except json.JSONDecodeError:
            candidate = re.match(r"\{.*\}", raw[start:], re.DOTALL)
            if not candidate:
                continue
            repaired = re.sub(r",\s*([}\]])", r"\1", candidate.group())
            try:
                data = json.loads(repaired)
            except json.JSONDecodeError:
                continue
        if isinstance(data, dict):
            return data

    raise ValueError("Could not parse a valid JSON object from model output.")


def _normalize_roast(data: dict) -> dict:
    """
    Free-tier models sometimes use slightly different key names
    ("roasts" instead of "roast_lines", "roast"/"joke" instead of "line",
    "closing" instead of "overall"). Normalize whatever comes back into
    the one shape the rest of the app expects.
    """
    raw_lines = data.get("roast_lines") or data.get("roasts") or data.get("roast") or []
    if not isinstance(raw_lines, list):
        raw_lines = []
    normalized = []
    for item in raw_lines:
        if not isinstance(item, dict):
            continue
        line = item.get("line") or item.get("roast") or item.get("joke") or ""
        fix = item.get("fix") or item.get("suggestion") or item.get("improvement") or ""
        if line:
            normalized.append({"line": str(line), "fix": str(fix)})

    overall = data.get("overall") or data.get("closing") or data.get("summary") or ""
    if not isinstance(overall, str):
        overall = str(overall)

    raw_score: Any = data.get("score")
    try:
        if not isinstance(raw_score, (int, float, str)):
            raise TypeError("score must be numeric")
        score = float(raw_score)
        score = max(0.0, min(10.0, score))  # clamp into 0-10 range
    except (TypeError, ValueError):
        # model omitted or mangled the score — fall back to a neutral
        # midpoint rather than crashing the whole roast on a missing number
        score = 5.0

    return {"roast_lines": normalized, "overall": overall, "score": round(score, 1)}

def generate_roast(resume_text: str, spice_level: str = "Medium") -> dict:
    resume_text = _clean_text(resume_text)[:4000]

    tone_guide = {
        "Mild": "warm and encouraging, with light observations",
        "Medium": "direct, constructive, and personable",
        "Well Done": "very candid but respectful and solution-focused",
    }[spice_level]

    prompt = f"""Review the résumé below with a {tone_guide} tone.
Focus only on clarity, structure, specificity, relevance, and presentation.
Create 4 to 6 concise observations grounded in the résumé. Every observation
must include a practical improvement. Do not judge the person or discuss
sensitive traits. Give a score from 0 to 10 and one encouraging closing sentence.

Résumé:
---
{resume_text}
---
"""

    response_schema = {
        "type": "OBJECT",
        "properties": {
            "score": {"type": "NUMBER"},
            "roast_lines": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "line": {"type": "STRING"},
                        "fix": {"type": "STRING"},
                    },
                    "required": ["line", "fix"],
                },
            },
            "overall": {"type": "STRING"},
        },
        "required": ["score", "roast_lines", "overall"],
    }

    try:
        client = get_client()

        chat = client.chats.create(
            model=MODEL,
            config=types.GenerateContentConfig(
                system_instruction="Return only valid JSON matching the requested shape.",
                temperature=0.3,
                max_output_tokens=1600,
                response_mime_type="application/json",
                response_schema=response_schema,
            ),
        )
        response = chat.send_message(prompt)
        log_token_usage(response, "roast")

        raw = response.text
        print(f"Gemini roast API response: {raw!r}", flush=True)

        if not raw:
            raise ValueError("Gemini returned an empty response.")

        st.code(raw, language="json")
        data = _extract_json_object(raw)

        return _normalize_roast(data)

    except Exception as e:
        print(f"Gemini roast error: {type(e).__name__}: {e!r}", flush=True)
        raise


def generate_roast_with_retry(
    resume_text: str,
    spice_level: str = "Medium",
    attempts: int = 3
) -> dict:
    """Retries if the roast generation fails."""

    last_error = None

    for _ in range(attempts):
        try:
            result = generate_roast(resume_text, spice_level)

            if result["roast_lines"]:
                return result

        except Exception as e:
            last_error = e

    raise RuntimeError(
        f"Gemini Roast failed | "
        f"Type={type(last_error).__name__} | "
        f"Error={str(last_error)} | "
        f"Model={MODEL}"
    ) from last_error

def roast_to_speech_text(roast: dict) -> str:
    """Flattens the roast into a natural spoken script for TTS."""
    parts = []
    for item in roast.get("roast_lines", []):
        parts.append(item["line"])
    parts.append(roast.get("overall", ""))
    return " ... ".join(p for p in parts if p)
