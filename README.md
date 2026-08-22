# Voice Résumé Builder + Roaster 🎙️🔥

Two modes in one app:

- **Build**: speak your work history out loud, section by section — no
  forms — and get a polished, downloadable résumé (.docx) with a matching
  header banner and a spoken confirmation of what was captured.
- **Roast**: upload an existing résumé (or roast the one you just built)
  and get a witty, honest critique — every joke is paired with a real,
  actionable fix, read aloud, with a shareable roast badge image.

## Why this is a good capstone scope

Every required technology has one clear job, and both flows are single
straight lines (no branching state machine, no live camera feed), which
makes it fast to build and reliable to demo:

```
BUILD MODE
Voice (per section) ──► faster-whisper (local STT) ──► raw transcript
                                                              │
                                                              ▼
                                            Gemini API (free tier)
                                     structures rambling speech into
                                     clean résumé text per section
                                                              │
                          ┌───────────────────────────────────┤
                          ▼                                   ▼
              Pollinations.ai (free image gen)        python-docx
              header banner matching target role      renders final .docx
                          │                                   │
                          └───────────────┬───────────────────┘
                                           ▼
                                 Streamlit review page
                                           │
                                           ▼
                              edge-tts (free TTS) reads back
                              a spoken confirmation summary

ROAST MODE
Uploaded résumé (.docx/.pdf/.txt) ──► text extraction (python-docx / pypdf)
        or résumé just built  ─┘
                    │
                    ▼
          Gemini API (free tier)
   generates roast lines, each paired
        with a real, actionable fix
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
Pollinations.ai            edge-tts
roast badge image      reads the roast aloud
```

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env      # add your free GEMINI_API_KEY from aistudio.google.com/apikey
streamlit run app.py
```

First run downloads the Whisper `base` model (~140MB) once, then STT runs
fully offline. TTS and the header image both call free, keyless public
endpoints — only the LLM structuring step needs your Gemini key, and Gemini's
free tier costs nothing to use for a project at this scale.

### Streamlit Cloud

Add this to the app's Secrets section under **Manage app > Settings > Secrets**:

```toml
GEMINI_API_KEY = "your-gemini-api-key"
```

After changing the secret, reboot the app. The local `.env` file is not used by
the deployed Streamlit Cloud app.

## Project structure

```
voice_resume_builder/
├── app.py                  # Streamlit UI: mode select → build or roast flow
├── requirements.txt
├── .env.example
└── modules/
    ├── audio_utils.py      # faster-whisper STT + edge-tts TTS
    ├── llm_engine.py       # structures rough speech into résumé text (Gemini)
    ├── roast_engine.py     # extracts résumé text + generates the roast (Gemini)
    ├── image_gen.py        # free header banner + roast badge (Pollinations.ai)
    └── resume_builder.py   # renders the structured résumé into a .docx
```

## Things worth mentioning in a capstone defense

- **Every API call is isolated in its own module** — `llm_engine.py` and
  `roast_engine.py` for reasoning, `image_gen.py` for visuals,
  `audio_utils.py` for voice — so swapping any one provider only touches
  one file.
- **The roast is grounded, not generic**: the prompt explicitly requires
  every joke to reference something actually in the résumé text and to be
  paired with a real fix — this is what separates it from a novelty joke
  generator and keeps it defensible as an actual feedback tool.
- **Roasts target the writing, never the person**: the prompt explicitly
  scopes humor to résumé content and formatting choices, not the
  candidate — worth calling out directly if a panel asks about the
  humor angle.
- **Graceful degradation**: if the free image endpoint is ever down,
  `generate_header_banner` returns `None` and the app just skips the
  banner rather than crashing the whole résumé build — a small but real
  system-design decision worth pointing out.
- **The transcript is never thrown away** — each raw transcript is kept
  in session state and shown next to the structured output, so a user
  (or a panel) can see exactly what the LLM changed and verify nothing
  was invented.
- **Honest scope**: this doesn't try to be an ATS-optimization tool or a
  design engine — it solves one specific, real friction point (typing out
  a résumé from scratch is tedious; talking through your history isn't)
  and does it well end to end.

## Known limitations to be upfront about

- The LLM is instructed not to invent facts, but like any LLM it can
  occasionally over-polish a bullet point — the review screen exists
  specifically so nothing goes into the final download unchecked.
- `.docx` styling is intentionally plain (no columns, no icons) so it
  renders correctly in any version of Word — trading visual flair for
  reliability, which is a reasonable, explainable choice for a résumé
  document specifically.
