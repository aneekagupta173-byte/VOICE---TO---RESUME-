"""
image_gen.py
Free, keyless image generation via Pollinations.ai — no signup, no API key,
no billing. Used for two things in this app:

  1. A header banner for the résumé, styled to the target role/industry.
  2. A playful "roast card" badge for the résumé roast feature.

If the service is ever unreachable, both functions return None and the app
falls back gracefully (skips the image) rather than breaking the flow.
"""

import urllib.parse

import requests

BASE_URL = "https://image.pollinations.ai/prompt/"


def _fetch(prompt: str, width: int, height: int) -> bytes | None:
    encoded = urllib.parse.quote(prompt)
    url = f"{BASE_URL}{encoded}?width={width}&height={height}&nologo=true"
    try:
        resp = requests.get(url, timeout=25)
        resp.raise_for_status()
        return resp.content
    except requests.RequestException:
        return None


def generate_header_banner(target_role: str) -> bytes | None:
    prompt = (
        f"minimalist abstract banner background representing the profession "
        f"of {target_role}, flat design, subtle geometric shapes, "
        f"professional color palette, no text, no people, wide aspect ratio"
    )
    return _fetch(prompt, width=1024, height=280)


def generate_roast_card(spice_level: str) -> bytes | None:
    """A playful badge-style image for the résumé roast result screen."""
    prompt = (
        f"minimalist flat-design badge illustration, comedic flame and trophy icons, "
        f"'{spice_level} roast' theme, bright playful color palette, no text, "
        f"no people, square composition"
    )
    return _fetch(prompt, width=500, height=500)
