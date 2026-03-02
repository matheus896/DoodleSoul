"""
Video generation tests using the Veo model via the Gemini API.

WARNING: Video generation consumes significant API quota and typically
takes 2-5 minutes per request. These tests are marked @pytest.mark.slow
and excluded from normal runs by default.

To run slow tests explicitly:
    pytest -m slow

To skip slow tests (default behavior):
    pytest -m "not slow"

Cost note: Each Veo request consumes credits. Do not run in CI pipelines
without budget controls. Requires Veo API access enabled on the project.
"""

import time

import pytest
from google.genai import types

MODEL = "veo-3.0-fast-generate-001"

PROMPT = (
    "A calm aerial timelapse of white clouds slowly drifting over green mountains "
    "during golden hour. Cinematic, smooth camera."
)

POLL_INTERVAL_SECONDS = 20
MAX_POLL_ATTEMPTS = 30  # 30 * 20s = up to 10 minutes


@pytest.mark.slow
class TestVideoGeneration:

    def test_generate_short_video(self, client, output_dir):
        """
        Generate a short video using the Veo fast model and save it to disk.

        COST WARNING: This test calls the Veo API which consumes quota.
        Run only with: pytest -m slow

        The test polls the long-running operation every 20 seconds until
        the video is ready, then saves the result to tests/output/.
        """
        # Start the generation — returns a long-running operation
        operation = client.models.generate_videos(
            model=MODEL,
            prompt=PROMPT,
            config=types.GenerateVideosConfig(
                number_of_videos=1,
                duration_seconds=8,
                aspect_ratio="16:9",
            ),
        )

        # Poll until the operation completes or we exceed the timeout
        attempts = 0
        while not operation.done:
            assert attempts < MAX_POLL_ATTEMPTS, (
                f"Video generation did not complete after "
                f"{MAX_POLL_ATTEMPTS * POLL_INTERVAL_SECONDS} seconds."
            )
            time.sleep(POLL_INTERVAL_SECONDS)
            operation = client.operations.get(operation)
            attempts += 1

        # Assert the response contains generated videos
        generated_videos = operation.response.generated_videos
        assert generated_videos is not None, "generated_videos should not be None"
        assert len(generated_videos) > 0, "At least one video should be generated"

        # Download and save each generated video
        for i, generated_video in enumerate(generated_videos):
            client.files.download(file=generated_video.video)
            output_path = output_dir / f"generated_video_{i}.mp4"
            generated_video.video.save(str(output_path))

            assert output_path.exists(), f"Video file was not saved to {output_path}"
            assert output_path.stat().st_size > 0, f"Video file at {output_path} is empty"
