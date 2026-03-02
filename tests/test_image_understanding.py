"""
Image understanding tests using the Gemini API.

Tests that gemini-2.5-flash can analyze images provided as:
1. A PIL.Image object (passed directly)
2. Raw bytes via types.Part.from_bytes

Both tests use a programmatically created image (solid red rectangle)
so there are no external file dependencies.
"""

import io

from PIL import Image
from google.genai import types

MODEL = "gemini-2.5-flash"


def _make_red_rectangle() -> Image.Image:
    """Return a 200x200 solid red PIL image."""
    return Image.new("RGB", (200, 200), color=(255, 0, 0))


class TestImageUnderstanding:

    def test_analyze_pil_image(self, client):
        """
        Pass a PIL.Image directly to generate_content.

        The google-genai SDK accepts PIL.Image objects natively inside
        the contents list without any manual serialization.
        """
        img = _make_red_rectangle()

        response = client.models.generate_content(
            model=MODEL,
            contents=[img, "What color is this image? Give a one-sentence answer."],
        )

        assert response.text is not None, "response.text should not be None"
        assert len(response.text) > 0, "response.text should not be empty"

    def test_analyze_image_from_bytes(self, client):
        """
        Pass image bytes using types.Part.from_bytes.

        Useful when image data is already in memory (e.g. from a network
        request) without needing to construct a PIL image.
        """
        img = _make_red_rectangle()

        # Serialize PIL image to PNG bytes in memory
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        img_bytes = buffer.getvalue()

        image_part = types.Part.from_bytes(data=img_bytes, mime_type="image/png")

        response = client.models.generate_content(
            model=MODEL,
            contents=[image_part, "What color is this image? Give a one-sentence answer."],
        )

        assert response.text is not None, "response.text should not be None"
        assert len(response.text) > 0, "response.text should not be empty"
