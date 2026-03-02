"""
Video understanding tests using the Gemini API.

Tests that gemini-2.5-flash can analyze a YouTube video provided via URI.
No video file is downloaded locally — the API fetches it directly from YouTube.
"""

from google.genai import types

MODEL = "gemini-2.5-flash"

# Big Buck Bunny — short, public, clearly identifiable animated video.
YOUTUBE_URL = "https://www.youtube.com/watch?v=aqz-KE-bpKQ"


class TestVideoUnderstanding:

    def test_analyze_youtube_video(self, client):
        """
        Pass a YouTube video URL via types.FileData and assert the model
        returns a non-empty description.

        The Gemini API accepts YouTube URIs directly without requiring
        a pre-upload through the Files API.
        """
        video_part = types.Part(
            file_data=types.FileData(
                file_uri=YOUTUBE_URL,
            )
        )

        response = client.models.generate_content(
            model=MODEL,
            contents=[video_part, "Briefly describe what you see in this video."],
        )

        assert response.text is not None, "response.text should not be None"
        assert len(response.text) > 0, "response.text should not be empty"
