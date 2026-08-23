"""
app.py
Voice Résumé Builder — Streamlit app.

Two modes, chosen at the start:

  BUILD  1. Basic info (name, contact, target role) — typed, short/exact
         2. Speak each section (Summary, Experience, Education, Skills) ->
            transcribed locally (faster-whisper) -> structured by an LLM
             call (Gemini, free tier)
         3. A header banner image is generated matching the target role
            (Pollinations.ai, free, no key)
         4. Preview, hear a spoken confirmation (edge-tts), download .docx

  ROAST  1. Upload an existing résumé (.docx/.pdf/.txt) or roast the one
            just built in this session
         2. Pick a spice level (Mild / Medium / Well Done)
         3. LLM generates roast lines, each paired with a real fix
         4. Hear it read aloud (edge-tts) + a generated roast badge image
"""

import tempfile
from pathlib import Path

import streamlit as st
from google.genai.errors import APIError

from modules import audio_utils, llm_engine, image_gen, resume_builder, roast_engine, history

st.set_page_config(page_title="Voice Résumé Builder", page_icon="🎙️", layout="centered")
history.init_db()

SECTIONS = [
    ("summary", "Summary", "In a sentence or two, describe your professional background "
                            "and what kind of role you're looking for."),
    ("experience", "Experience", "Talk through your work history: job titles, companies, "
                                  "roughly how long, and what you actually did or achieved."),
    ("education", "Education", "Talk through your education: degrees, schools, and years."),
    ("skills", "Skills", "List out your key skills — tools, languages, frameworks, "
                          "or strengths you want on the résumé."),
]

defaults = {
    "stage": "mode_select",
    "transcripts": {},
    "resume": {},
    "banner_bytes": None,
    "roast_result": None,
    "roast_card_bytes": None,
    "roast_audio": None,
    "roast_source_text": None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


def reset_all():
    for k, v in defaults.items():
        st.session_state[k] = v


def render_back_to_home():
    if st.session_state.stage != "mode_select":
        if st.button("← Back to Home", key="back_to_home"):
            reset_all()
            st.rerun()


st.title("🎙️ Voice Résumé Builder")
st.caption("Speak your work history into a polished résumé — or upload one "
           "and get it roasted.")
render_back_to_home()

def _has_gemini_key() -> bool:
    try:
        return bool(st.secrets.get("GEMINI_API_KEY") or st.secrets.get("gemini_api"))
    except Exception:
        return False


if not _has_gemini_key():
    st.warning("GEMINI_API_KEY not set — get a free key at aistudio.google.com/apikey and "
               "add it to Streamlit Secrets before structuring sections.", icon="⚠️")

# ---------------------------------------------------------------- STAGE 0: mode select
if st.session_state.stage == "mode_select":
    st.subheader("What do you want to do?")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### 🛠️ Build a résumé")
        st.caption("Speak your work history and get a polished, downloadable résumé.")
        if st.button("Build my résumé →", type="primary", use_container_width=True):
            st.session_state.stage = "basics"
            st.rerun()
    with col2:
        st.markdown("### 🔥 Roast my résumé")
        st.caption("Upload an existing résumé and get a witty, honest critique.")
        if st.button("Roast my résumé →", use_container_width=True):
            st.session_state.stage = "roast_upload"
            st.rerun()

# ---------------------------------------------------------------- STAGE 1: basics
elif st.session_state.stage == "basics":
    st.subheader("Basic info")
    with st.form("basics_form", border=True):
        name = st.text_input("Full name")
        col1, col2 = st.columns(2)
        with col1:
            email = st.text_input("Email")
            target_role = st.text_input("Target role", placeholder="e.g. Marketing Coordinator")
        with col2:
            phone = st.text_input("Phone (optional)")
            location = st.text_input("Location (optional)")
        submitted = st.form_submit_button("Continue →", type="primary")

    if submitted:
        if not (name and email and target_role):
            st.error("Please fill in your name, email, and target role.")
        else:
            st.session_state.resume.update({
                "name": name, "email": email, "phone": phone,
                "location": location, "target_role": target_role,
            })
            st.session_state.stage = "sections"
            st.rerun()

# ---------------------------------------------------------------- STAGE 2: voice sections
elif st.session_state.stage == "sections":
    st.subheader("Speak each section")
    st.caption(f"Target role: **{st.session_state.resume.get('target_role')}**")

    for key, label, prompt in SECTIONS:
        done = key in st.session_state.transcripts
        with st.expander(f"{'✅' if done else '🎤'} {label}", expanded=not done):
            st.write(prompt)
            with st.form(f"form_{key}", border=False):
                recorded = st.audio_input("Record your answer", key=f"rec_{key}")
                submitted = st.form_submit_button("Transcribe this section")

            if submitted:
                if recorded is None:
                    st.warning("Record an answer before transcribing.")
                else:
                    with st.spinner("Transcribing..."):
                        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                            tmp.write(recorded.getvalue())
                            tmp_path = tmp.name
                        transcript = audio_utils.transcribe_audio(tmp_path)
                        Path(tmp_path).unlink(missing_ok=True)
                    st.session_state.transcripts[key] = transcript
                    st.rerun()

            if done:
                st.text_area("Transcript (auto-captured)", st.session_state.transcripts[key],
                              key=f"ta_{key}", height=100)

    all_done = all(k in st.session_state.transcripts for k, _, _ in SECTIONS)
    if st.button("Build my résumé →", type="primary", disabled=not all_done):
        st.session_state.stage = "building"
        st.rerun()

# ---------------------------------------------------------------- STAGE 3: build (LLM + image)
elif st.session_state.stage == "building":
    st.subheader("Putting it together...")
    role = st.session_state.resume.get("target_role", "")
    t = st.session_state.transcripts

    try:
        with st.spinner("Writing your summary..."):
            st.session_state.resume["summary"] = llm_engine.structure_summary(t["summary"], role)

        with st.spinner("Structuring your experience..."):
            st.session_state.resume["experience"] = llm_engine.structure_experience(t["experience"])

        with st.spinner("Structuring your education..."):
            st.session_state.resume["education"] = llm_engine.structure_education(t["education"])

        with st.spinner("Extracting your skills..."):
            st.session_state.resume["skills"] = llm_engine.structure_skills(t["skills"])

        with st.spinner("Generating a header banner..."):
            st.session_state.banner_bytes = image_gen.generate_header_banner(role)
    except RuntimeError as error:
        st.error(str(error))
        st.info("Add GEMINI_API_KEY under Streamlit Secrets, then reboot the app.")
        st.stop()
    except APIError as error:
        st.error(f"Gemini rejected the résumé request: {error}")
        st.info("Check the Gemini API key, model access, and API quota, then try again.")
        st.stop()
    except (KeyError, ValueError, TypeError) as error:
        st.error(f"The résumé response was not in the expected format: {error}")
        st.info("Please try building the résumé again after checking that each section has a transcript.")
        st.stop()

    st.session_state.stage = "review"
    st.rerun()

# ---------------------------------------------------------------- STAGE 4: review + download
elif st.session_state.stage == "review":
    resume = st.session_state.resume

    if st.session_state.banner_bytes:
        st.image(st.session_state.banner_bytes, use_container_width=True)

    st.header(resume.get("name", ""))
    contact_line = " | ".join(x for x in [resume.get("email"), resume.get("phone"),
                                           resume.get("location")] if x)
    st.caption(contact_line)

    st.markdown("### Summary")
    st.write(resume.get("summary", ""))

    st.markdown("### Experience")
    for job in resume.get("experience", []):
        st.markdown(f"**{job.get('title', '')}** — {job.get('company', '')} "
                    f"({job.get('duration', '')})")
        for b in job.get("bullets", []):
            st.markdown(f"- {b}")

    st.markdown("### Education")
    for edu in resume.get("education", []):
        st.markdown(f"**{edu.get('degree', '')}** — {edu.get('institution', '')} "
                    f"({edu.get('year', '')})")

    st.markdown("### Skills")
    st.write(", ".join(resume.get("skills", [])))

    st.divider()
    st.subheader("🗣️ Spoken confirmation")
    if "confirmation_audio" not in st.session_state:
        with st.spinner("Preparing spoken summary..."):
            confirmation_text = llm_engine.generate_confirmation_summary(resume)
            st.session_state.confirmation_audio = audio_utils.synthesize_speech(confirmation_text)
            st.session_state.confirmation_text = confirmation_text
    st.write(st.session_state.confirmation_text)
    st.audio(st.session_state.confirmation_audio, format="audio/mp3")

    st.divider()
    docx_bytes = resume_builder.build_resume_docx(resume)
    st.download_button(
        "⬇️ Download résumé (.docx)", data=docx_bytes,
        file_name=f"{resume.get('name', 'resume').replace(' ', '_')}_resume.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        type="primary",
    )

    if st.button("Start over"):
        reset_all()
        st.rerun()

    st.divider()
    if st.button("🔥 Roast this résumé"):
        st.session_state.roast_source_text = roast_engine.resume_dict_to_text(resume)
        st.session_state.roast_result = None
        st.session_state.roast_card_bytes = None
        st.session_state.roast_audio = None
        st.session_state.stage = "roast_spice"
        st.rerun()

# ---------------------------------------------------------------- ROAST STAGE 1: upload
elif st.session_state.stage == "roast_upload":
    st.subheader("🔥 Roast my résumé")
    st.caption("Upload a résumé and pick how spicy you want the feedback.")

    with st.form("roast_upload_form", border=True):
        uploaded = st.file_uploader("Upload your résumé", type=["docx", "pdf", "txt"])
        submitted = st.form_submit_button("Continue →", type="primary")

    if submitted:
        if uploaded is None:
            st.warning("Please upload a résumé file first.")
        else:
            with st.spinner("Reading your résumé..."):
                st.session_state.roast_source_text = roast_engine.extract_text_from_upload(uploaded)
            st.session_state.stage = "roast_spice"
            st.rerun()

# ---------------------------------------------------------------- ROAST STAGE 2: spice level
elif st.session_state.stage == "roast_spice":
    st.subheader("🌶️ Pick your spice level")
    with st.form("roast_spice_form", border=True):
        spice = st.radio(
            "How honest do you want this?",
            ["Mild", "Medium", "Well Done"],
            index=1,
            captions=["Gentle and encouraging", "Witty and honest", "Savage but constructive"],
        )
        submitted = st.form_submit_button("Roast it →", type="primary")

    if submitted:
        with st.spinner("Reading your résumé and warming up..."):
            baseline_score = history.get_last_score()  # capture BEFORE saving the new one

            try:
                st.session_state.roast_result = roast_engine.generate_roast_with_retry(
                    st.session_state.roast_source_text, spice_level=spice
                )
            except RuntimeError as error:
                message = str(error)
                if "GEMINI_API_KEY not set" in message:
                    st.error("Gemini key is missing. Add GEMINI_API_KEY in Manage app > Settings > Secrets, then reboot the app.")
                else:
                    st.error("Gemini rejected the roast request. Check that your key is active, then try again.")
                st.stop()
            st.session_state.roast_card_bytes = image_gen.generate_roast_card(spice)
            speech_text = roast_engine.roast_to_speech_text(st.session_state.roast_result)
            st.session_state.roast_audio = audio_utils.synthesize_speech(
                speech_text, voice="en-US-GuyNeural"
            )

            history.save_roast(
                spice, st.session_state.roast_result["score"],
                st.session_state.roast_result.get("overall", "")
            )
            st.session_state.roast_score_baseline = baseline_score

        st.session_state.stage = "roast_result"
        st.rerun()

# ---------------------------------------------------------------- ROAST STAGE 3: result
elif st.session_state.stage == "roast_result":
    roast = st.session_state.roast_result
    st.subheader("🔥 The roast")

    score = roast.get("score", 5.0)
    baseline = st.session_state.get("roast_score_baseline")
    delta_str = f"{score - baseline:+.1f}" if baseline is not None else None

    col1, col2 = st.columns([1, 2])
    with col1:
        st.metric("Résumé score", f"{score:.1f}/10", delta=delta_str)
    with col2:
        if baseline is not None:
            st.caption(f"Compared to your last roast ({baseline:.1f}/10).")
        else:
            st.caption("This is your first roast — future ones will show a trend.")

    if st.session_state.roast_card_bytes:
        st.image(st.session_state.roast_card_bytes, width=220)

    if st.session_state.roast_audio:
        st.audio(st.session_state.roast_audio, format="audio/mp3")

    for item in roast.get("roast_lines", []):
        with st.container(border=True):
            st.markdown(f"🔥 {item['line']}")
            st.markdown(f"✅ **Fix:** {item['fix']}")

    st.success(roast.get("overall", ""))

    st.divider()
    st.subheader("📊 Your roast history")
    hist_df = history.get_history_df()
    if hist_df.empty:
        st.caption("History will build up here as you roast more résumés.")
    else:
        display_df = hist_df.copy()
        display_df["created_at"] = display_df["created_at"].dt.strftime("%Y-%m-%d %H:%M")
        display_df["reviewed"] = False  # lets you tick off ones you've acted on
        st.data_editor(
            display_df[["created_at", "spice_level", "score", "reviewed"]],
            column_config={
                "created_at": st.column_config.TextColumn("Date"),
                "spice_level": st.column_config.TextColumn("Spice"),
                "score": st.column_config.NumberColumn("Score", format="%.1f /10"),
                "reviewed": st.column_config.CheckboxColumn("Fixed it?"),
            },
            hide_index=True,
            use_container_width=True,
            key="roast_history_editor",
        )

    st.divider()
    if st.button("Roast another résumé"):
        st.session_state.stage = "roast_upload"
        st.session_state.roast_result = None
        st.rerun()
