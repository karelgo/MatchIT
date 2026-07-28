"""Speech → text for asynchronous interview answers.

MatchIT does not do video interviews, and that is a position rather than a gap:
AI video interviewing is the subject of the ACLU's complaint against HireVue and
of *Baker v. CVS*, and it sits uncomfortably close to the EU AI Act's outright
prohibition on inferring emotions in a workplace context. Voice, on the other
hand, is genuinely useful — some people think better out loud, and typing four
paragraphs on a phone is a barrier that has nothing to do with competence.

So the answer is voice *in*, text *scored*. Audio is transcribed and discarded;
the transcript is what is stored, what the assessor reads and what appears in the
transparency report. Nothing infers accent, affect, confidence or fluency from
the recording, because the recording does not survive the request.
"""

from typing import Protocol

MAX_AUDIO_BYTES = 25 * 1024 * 1024  # the practical ceiling for hosted ASR endpoints

# Container formats the hosted transcription APIs accept.
ALLOWED_AUDIO_SUFFIXES = frozenset(
    {".m4a", ".mp3", ".mp4", ".mpeg", ".mpga", ".oga", ".ogg", ".wav", ".webm", ".flac"}
)


class TranscriptionError(Exception):
    """The audio cannot be turned into text; the message is user-facing."""


class Transcriber(Protocol):
    async def transcribe(
        self, audio: bytes, *, filename: str, language: str | None = None
    ) -> str: ...


class OpenAITranscriber:
    """Hosted speech-to-text.

    `language` is passed when the caller knows it: an ASR model guessing the
    language of a Dutch speaker answering in English is a common and entirely
    avoidable source of garbled transcripts.
    """

    def __init__(self, api_key: str, model: str):
        import openai

        self._client = openai.AsyncOpenAI(api_key=api_key)
        self._model = model

    async def transcribe(
        self, audio: bytes, *, filename: str, language: str | None = None
    ) -> str:
        import openai

        try:
            response = await self._client.audio.transcriptions.create(
                model=self._model,
                file=(filename, audio),
                language=language or openai.NOT_GIVEN,
                response_format="text",
            )
        except openai.OpenAIError as error:
            raise TranscriptionError(
                "The audio could not be transcribed. Try again, or type your answer."
            ) from error
        text = (response if isinstance(response, str) else str(response)).strip()
        if not text:
            raise TranscriptionError(
                "No speech was detected in that recording. Check your microphone, or "
                "type your answer instead."
            )
        return text


class FakeTranscriber:
    """Deterministic transcriber for tests."""

    def __init__(self, text: str = "This is a spoken answer, transcribed."):
        self.text = text
        self.calls: list[dict] = []

    async def transcribe(
        self, audio: bytes, *, filename: str, language: str | None = None
    ) -> str:
        self.calls.append({"bytes": len(audio), "filename": filename, "language": language})
        return self.text


class DisabledTranscriber:
    """Refuses clearly rather than failing obscurely when no provider is configured.

    Typing an answer always works, so a missing ASR provider degrades one input
    method rather than blocking the interview.
    """

    async def transcribe(
        self, audio: bytes, *, filename: str, language: str | None = None
    ) -> str:
        raise TranscriptionError(
            "Voice answers are not available on this deployment. Type your answer instead."
        )


def check_audio(data: bytes, filename: str) -> None:
    """Validate before spending anything on a transcription call."""
    suffix = filename[filename.rfind(".") :].lower() if "." in filename else ""
    if suffix not in ALLOWED_AUDIO_SUFFIXES:
        supported = ", ".join(sorted(ALLOWED_AUDIO_SUFFIXES))
        raise TranscriptionError(
            f"Unsupported audio format '{suffix or filename}'. Use one of: {supported}."
        )
    if not data:
        raise TranscriptionError("The recording is empty.")
    if len(data) > MAX_AUDIO_BYTES:
        raise TranscriptionError("That recording is over 25 MB; record a shorter answer.")


def build_transcriber(settings) -> Transcriber:
    if settings.transcription_provider == "openai":
        if not settings.openai_api_key:
            return DisabledTranscriber()
        return OpenAITranscriber(settings.openai_api_key, settings.transcription_model)
    if settings.transcription_provider == "fake":
        return FakeTranscriber()
    if settings.transcription_provider == "off":
        return DisabledTranscriber()
    raise ValueError(f"unknown transcription_provider: {settings.transcription_provider}")
