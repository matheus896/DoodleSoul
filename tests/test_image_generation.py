"""
Image generation tests using the Gemini Nano Banana model.

Tests that gemini-2.5-flash-image generates at least one image part
in its response. The generated image is saved to tests/output/ for
manual inspection after the test run.
"""

from google.genai import types

MODEL = "gemini-3.1-flash-image-preview"

PROMPT = "A simple illustration of a single Robot holding a red apple on a white background."


class TestImageGeneration:

    def test_generate_image(self, client, output_dir):
        """
        Request an image from the Nano Banana model and assert that at
        least one image part is returned in the response.

        response_modalities must be set to ["IMAGE", "TEXT"] — without it
        the model may return only text and never produce inline_data.
        """
        response = client.models.generate_content(
            model=MODEL,
            contents=PROMPT,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
            ),
        )

        # Collect all parts across all candidates
        all_parts = [
            part
            for candidate in response.candidates
            for part in candidate.content.parts
        ]

        # Assert at least one part carries inline image data
        image_parts = [p for p in all_parts if p.inline_data is not None]
        assert len(image_parts) > 0, (
            "Expected at least one image part in the response, "
            f"but found none. Parts returned: {len(all_parts)}"
        )

        # Save the first generated image for inspection
        first_image = image_parts[0]
        mime_type = first_image.inline_data.mime_type  # e.g. "image/png"
        extension = mime_type.split("/")[-1]            # e.g. "png"
        output_path = output_dir / f"generated_image.{extension}"

        with open(output_path, "wb") as f:
            f.write(first_image.inline_data.data)

        assert output_path.exists(), f"Image file was not saved to {output_path}"
