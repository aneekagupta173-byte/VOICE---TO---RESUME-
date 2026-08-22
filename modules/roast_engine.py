"""
roast_engine.py
The "Roast My Résumé" feature: extracts plain text from an uploaded résumé
(.docx, .pdf, or .txt) or from a résumé this app just built, then asks the
LLM for a funny-but-genuinely-useful critique — not just jokes, each roast
line is paired with a real, actionable fix.

IMPORTANT: this does NOT use Groq's strict response_format="json_object"
mode. That mode makes Groq hard-reject the entire request (a 400 error)
if the model's raw output isn't perfectly clean JSON — and free-tier
models occasionally drift (wrong key names, or a stray sentence before
the JSON). Instead we take whatever text comes back and parse it
ourselves, forgiving both extra text around the JSON and slightly wrong
key names — so a small model quirk degrades gracefully instead of
crashing the app.
"""

import io
import json
import re

from docx import Document
from pypdf import PdfReader

from modules.llm_engine import get_client, MODEL


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
    raw = raw.strip()
    if "```json" in raw:
        raw = raw.split("```json")[-1]
    raw = raw.replace("```", "").strip()

    start = raw.find("{")
    if start == -1:
        raise ValueError("No JSON object found in model output.")

    depth = 0
    for i in range(start, len(raw)):
        if raw[i] == "{":
            depth += 1
        elif raw[i] == "}":
            depth -= 1
            if depth == 0:
                candidate = raw[start:i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    continue
    raise ValueError("Could not parse a valid JSON object from model output.")


def _normalize_roast(data: dict) -> dict:
    """
    Free-tier models sometimes use slightly different key names
    ("roasts" instead of "roast_lines", "roast"/"joke" instead of "line",
    "closing" instead of "overall"). Normalize whatever comes back into
    the one shape the rest of the app expects.
    """
    raw_lines = data.get("roast_lines") or data.get("roasts") or data.get("roast") or []
    normalized = []
    for item in raw_lines:
        if not isinstance(item, dict):
            continue
        line = item.get("line") or item.get("roast") or item.get("joke") or ""
        fix = item.get("fix") or item.get("suggestion") or item.get("improvement") or ""
        if line:
            normalized.append({"line": line, "fix": fix})

    overall = data.get("overall") or data.get("closing") or data.get("summary") or ""

    raw_score = data.get("score")
    try:
        score = float(raw_score)
        score = max(0.0, min(10.0, score))  # clamp into 0-10 range
    except (TypeError, ValueError):
        # model omitted or mangled the score — fall back to a neutral
        # midpoint rather than crashing the whole roast on a missing number
        score = 5.0

    return {"roast_lines": normalized, "overall": overall, "score": round(score, 1)}


def generate_roast(resume_text: str, spice_level: str = "Medium") -> dict:
    """
    spice_level: "Mild" (gentle, mostly encouraging), "Medium" (witty, honest),
    or "Well Done" (savage but still constructive underneath).
    Returns {"roast_lines": [{"line": "...", "fix": "..."}], "overall": "..."}
    """
    resume_text = _clean_text(resume_text)[:4000]

    tone_guide = {
        "Mild": "gentle, encouraging humor — tease lightly, mostly compliment",
        "Medium": "witty and honest, like a sharp friend giving real feedback",
        "Well Done": "savage, comedy-roast energy — but never cruel or personal, "
                     "always aimed at the résumé content, not the person",
    }[spice_level]

    prompt = f"""You are a comedy roast writer who also happens to be a genuinely
excellent résumé reviewer. Roast the following résumé in a {tone_guide} style.

Rules:
- Give an honest overall résumé quality score from 0-10 (be a real critic —
  don't default to a lazy 7/10 for everything; a rough draft should score
  low, a genuinely strong résumé should score high).
- Every roast line MUST be paired with a real, specific, actionable fix — the
  humor is the hook, the fix is the actual value.
- Base every joke on something ACTUALLY in the résumé text below — never invent
  details that aren't there.
- Never insult the person themselves, their identity, or anything outside the
  résumé content itself — keep it about the writing, formatting, and choices.
- 4-6 roast lines total, plus one overall closing line that's encouraging.
- Output ONLY the JSON object below. Do not repeat, quote, or reformat the
  résumé text anywhere in your response. Do not add commentary before or
  after the JSON.

Résumé text:
\"\"\"{resume_text}\"\"\"

Respond with EXACTLY this JSON shape and these exact key names, nothing else:
{{
  "score": <number 0-10>,
  "roast_lines": [{{"line": "<funny observation>", "fix": "<specific actionable fix>"}}],
  "overall": "<one encouraging closing sentence>"
}}"""

    resp = get_client().chat.completions.create(
        model=MODEL,
        max_tokens=900,
        temperature=0.5,
        messages=[{"role": "user", "content": prompt}],
        # NOTE: intentionally NOT using response_format="json_object" here —
        # that mode makes Groq hard-reject the whole request on any drift,
        # instead of giving us text we could still parse.
    )
    raw = resp.choices[0].message.content.strip()
    data = _extract_json_object(raw)
    return _normalize_roast(data)


def generate_roast_with_retry(resume_text: str, spice_level: str = "Medium", attempts: int = 3) -> dict:
    """Retries a couple of times if parsing fails, since a fresh call usually succeeds."""
    last_error = None
    for _ in range(attempts):
        try:
            result = generate_roast(resume_text, spice_level)
            if result["roast_lines"]:
                return result
        except Exception as e:
            last_error = e
    if last_error:
        raise last_error
    raise ValueError("Could not generate a roast after several attempts — try again.")


def roast_to_speech_text(roast: dict) -> str:
    """Flattens the roast into a natural spoken script for TTS."""
    parts = []
    for item in roast.get("roast_lines", []):
        parts.append(item["line"])
    parts.append(roast.get("overall", ""))
    return " ... ".join(p for p in parts if p)
