"""
Image generation tests using the Imagen 4 model.

Tests that imagen-4.0-generate-001 generates images from text prompts
using the generate_images API. Generated images are saved to tests/output/
for manual inspection after the test run.
"""

from google.genai import types

MODEL = "imagen-4.0-generate-001"

PROMPT = "Robot holding a red skateboard"


class TestImagenGeneration:

    def test_generate_single_image(self, client, output_dir):
        """
        Generate a single image with Imagen 4 and save it to disk.
        """
        response = client.models.generate_images(
            model=MODEL,
            prompt=PROMPT,
            config=types.GenerateImagesConfig(
                number_of_images=1,
            ),
        )

        assert response.generated_images is not None, "generated_images should not be None"
        assert len(response.generated_images) == 1, "Expected exactly 1 generated image"

        image = response.generated_images[0].image
        output_path = output_dir / "imagen_single.png"
        image.save(str(output_path))

        assert output_path.exists(), f"Image file was not saved to {output_path}"
        assert output_path.stat().st_size > 0, f"Image file at {output_path} is empty"

    def test_generate_multiple_images(self, client, output_dir):
        """
        Generate 4 images with Imagen 4 and save them all to disk.
        """
        response = client.models.generate_images(
            model=MODEL,
            prompt=PROMPT,
            config=types.GenerateImagesConfig(
                number_of_images=4,
            ),
        )

        assert response.generated_images is not None, "generated_images should not be None"
        assert len(response.generated_images) == 4, "Expected 4 generated images"

        for i, generated_image in enumerate(response.generated_images):
            output_path = output_dir / f"imagen_multi_{i}.png"
            generated_image.image.save(str(output_path))

            assert output_path.exists(), f"Image file was not saved to {output_path}"
            assert output_path.stat().st_size > 0, f"Image file at {output_path} is empty"
