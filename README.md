# Voice Resume Builder + Roaster

A Streamlit application that turns spoken work history into a downloadable
resume, or reviews an existing resume with constructive, actionable feedback.

## Features

### Build a resume

1. Enter basic contact information and a target role.
2. Record Summary, Experience, Education, and Skills sections.
3. Transcribe each recording locally with `faster-whisper`.
4. Send each transcript to Gemini for structured resume content.
5. Review the generated resume, hear a spoken confirmation, and download a
   `.docx` file.

### Roast a resume

Upload a `.docx`, `.pdf`, or `.txt` resume, or roast the resume created in the
same session. Gemini returns a score, several observations, and a practical
fix for every observation. The result can also be read aloud and rendered as
an image card.

## Technology

- **Streamlit**: user interface and session state
- **faster-whisper**: local speech-to-text
- **Gemini `gemini-3.6-flash`**: resume structuring and feedback
- **python-docx / pypdf**: resume file creation and text extraction
- **edge-tts**: spoken confirmation and roast audio
- **Pollinations.ai**: generated header and roast images

## Setup

Install the dependencies in the project virtual environment:

```powershell
pip install -r requirements.txt
```

Create `.streamlit/secrets.toml` locally, or add the same values under
**Manage app > Settings > Secrets** in Streamlit Cloud:

```toml
GEMINI_API_KEY = "your-gemini-api-key"
HF_TOKEN = "your-huggingface-read-token"
```

`GEMINI_API_KEY` is required for resume generation and roasting. `HF_TOKEN`
is a read-only Hugging Face User Access Token used to improve Whisper model
download limits. It is optional, but recommended.

Run the app:

```powershell
streamlit run app.py
```

The application reads API keys from Streamlit Secrets only. It does not use
`.env` files.

## Session API key override

The sidebar contains a password-style **Gemini API key** field. A user can
enter a temporary key there for the current session. The priority is:

1. Sidebar key, when entered.
2. `GEMINI_API_KEY` from Streamlit Secrets, when the sidebar is blank.

The sidebar key is held in Streamlit session state and is not written to the
repository or persisted as application configuration.

## JSON reliability

Gemini requests use `application/json` response mode and explicit schemas for
summary, experience, education, skills, and roast responses. The app also:

- Uses Gemini's structured `response.parsed` value when available.
- Handles harmless code fences, surrounding text, and trailing commas.
- Retries incomplete or empty section responses once.
- Rejects empty transcripts before sending them to Gemini.
- Logs response sections, finish reasons, and token usage for troubleshooting.

## Project structure

```text
voice_resume_builder/
├── app.py                  # Streamlit UI and build/roast workflows
├── requirements.txt        # Python dependencies
├── .streamlit/
│   └── secrets.toml.example # Secrets template; never add real keys here
└── modules/
    ├── audio_utils.py      # Whisper transcription and edge-tts audio
    ├── llm_engine.py       # Gemini client, schemas, and resume generation
    ├── roast_engine.py     # Resume extraction and Gemini roast generation
    ├── image_gen.py        # Pollinations.ai image generation
    ├── resume_builder.py   # Structured resume to .docx
    └── history.py          # Local roast score history
```

## Troubleshooting

- **No speech detected**: record the section again and speak clearly near the
  microphone. The Build button requires non-empty transcripts.
- **Missing Gemini key**: add `GEMINI_API_KEY` to Streamlit Secrets or enter
  a temporary key in the sidebar.
- **Whisper download warning**: add a read-only `HF_TOKEN` to Streamlit
  Secrets, then reboot the app.
- **JSON or section error**: check Streamlit logs for the section name,
  `finish_reason`, raw response, and token usage. Reboot after deploying code
  or changing secrets.

## Project scope

The app focuses on a clear workflow rather than ATS optimization or complex
resume design. Users can review the generated content before downloading it,
and the LLM is instructed to preserve stated facts instead of inventing
qualifications or achievements.
