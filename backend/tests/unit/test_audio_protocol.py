import pytest

from app.realtime.audio_protocol import AudioFormatError, validate_pcm16_16khz_mono


def test_accepts_pcm16_16khz_mono() -> None:
    validate_pcm16_16khz_mono(
        {"sample_rate": 16000, "channels": 1, "encoding": "pcm_s16le"}
    )


def test_rejects_non_16khz() -> None:
    with pytest.raises(AudioFormatError):
        validate_pcm16_16khz_mono(
            {"sample_rate": 48000, "channels": 1, "encoding": "pcm_s16le"}
        )


def test_rejects_non_mono() -> None:
    with pytest.raises(AudioFormatError):
        validate_pcm16_16khz_mono(
            {"sample_rate": 16000, "channels": 2, "encoding": "pcm_s16le"}
        )


def test_rejects_non_pcm_s16le() -> None:
    with pytest.raises(AudioFormatError):
        validate_pcm16_16khz_mono(
            {"sample_rate": 16000, "channels": 1, "encoding": "pcm_mulaw"}
        )
