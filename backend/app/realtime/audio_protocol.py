class AudioFormatError(ValueError):
    pass


def validate_pcm16_16khz_mono(metadata: dict[str, int | str]) -> None:
    sample_rate = metadata.get("sample_rate")
    channels = metadata.get("channels")
    encoding = metadata.get("encoding")

    if sample_rate != 16000 or channels != 1 or encoding != "pcm_s16le":
        raise AudioFormatError("Expected pcm_s16le / 16000Hz / mono")
