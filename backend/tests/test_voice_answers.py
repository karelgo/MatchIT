"""Spoken interview answers: transcribed, scored as text, audio never kept."""

import pytest

from app.services.transcription import (
    MAX_AUDIO_BYTES,
    DisabledTranscriber,
    FakeTranscriber,
    TranscriptionError,
    build_transcriber,
    check_audio,
)
from tests.conftest import auth_headers
from tests.test_chat import make_mutual_match
from tests.test_interviews import assessment_of, plan_of

AUDIO = b"\x00\x01fake-m4a-bytes"


async def _started_interview(client, fake_chat, *, prefix: str):
    specialist_tokens, company_tokens, match = await make_mutual_match(
        client, fake_chat, company_email=f"{prefix}-hm@example.com"
    )
    fake_chat.responses.append(plan_of())
    interview = (
        await client.post(
            f"/api/v1/matches/{match['id']}/interview", headers=auth_headers(company_tokens)
        )
    ).json()
    return specialist_tokens, company_tokens, match, interview


async def _post_audio(client, tokens, match_id, *, filename="answer.m4a", data=AUDIO, **params):
    return await client.post(
        f"/api/v1/matches/{match_id}/interview/answer/audio",
        headers=auth_headers(tokens),
        files={"file": (filename, data, "audio/mp4")},
        params=params,
    )


def test_audio_format_is_checked_before_anything_is_spent():
    check_audio(AUDIO, "answer.m4a")
    check_audio(AUDIO, "ANSWER.WAV")

    with pytest.raises(TranscriptionError, match="Unsupported audio format"):
        check_audio(AUDIO, "answer.txt")
    with pytest.raises(TranscriptionError, match="Unsupported audio format"):
        check_audio(AUDIO, "answer")
    with pytest.raises(TranscriptionError, match="empty"):
        check_audio(b"", "answer.m4a")
    with pytest.raises(TranscriptionError, match="over 25 MB"):
        check_audio(b"x" * (MAX_AUDIO_BYTES + 1), "answer.m4a")


def test_a_deployment_without_a_provider_refuses_clearly():
    """Typing always works, so a missing provider degrades one input method."""

    class _Settings:
        transcription_provider = "openai"
        transcription_model = "whisper-1"
        openai_api_key = ""

    transcriber = build_transcriber(_Settings())
    assert isinstance(transcriber, DisabledTranscriber)


def test_an_unknown_provider_fails_at_startup_not_at_use():
    class _Settings:
        transcription_provider = "typo"
        transcription_model = "whisper-1"
        openai_api_key = "sk-test"

    with pytest.raises(ValueError, match="unknown transcription_provider"):
        build_transcriber(_Settings())


async def test_a_spoken_answer_is_transcribed_into_the_transcript(
    client, fake_chat, transcriber
):
    transcriber.text = "I migrated a forty terabyte warehouse to Fabric over nine months."
    specialist_tokens, _, match, _ = await _started_interview(client, fake_chat, prefix="va-ok")

    response = await _post_audio(client, specialist_tokens, match["id"])
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["answered_count"] == 1
    entry = body["transcript"][0]
    assert entry["answer"] == transcriber.text
    assert entry["input_mode"] == "voice"
    assert transcriber.calls == [
        {"bytes": len(AUDIO), "filename": "answer.m4a", "language": None}
    ]


async def test_the_language_hint_is_passed_through(client, fake_chat, transcriber):
    """An ASR model guessing the language is an avoidable source of garbled text."""
    specialist_tokens, _, match, _ = await _started_interview(client, fake_chat, prefix="va-lang")
    await _post_audio(client, specialist_tokens, match["id"], language="nl")
    assert transcriber.calls[0]["language"] == "nl"


async def test_a_rejected_recording_costs_no_transcription(client, fake_chat, transcriber):
    specialist_tokens, _, match, _ = await _started_interview(client, fake_chat, prefix="va-bad")
    response = await _post_audio(client, specialist_tokens, match["id"], filename="answer.txt")

    assert response.status_code == 422
    assert "Unsupported audio format" in response.json()["detail"]
    assert transcriber.calls == []


async def test_typed_and_spoken_answers_share_one_path(client, fake_chat, transcriber):
    """Mixing input modes mid-interview must just work."""
    transcriber.text = "A spoken answer about a real migration."
    specialist_tokens, company_tokens, match, interview = await _started_interview(
        client, fake_chat, prefix="va-mix"
    )
    total = interview["total_questions"]

    await _post_audio(client, specialist_tokens, match["id"])
    for index in range(1, total):
        if index == total - 1:
            fake_chat.responses.append(assessment_of(0.8))
        response = await client.post(
            f"/api/v1/matches/{match['id']}/interview/answer",
            headers=auth_headers(specialist_tokens),
            json={"answer": f"A typed answer number {index}.", "input_mode": "text"},
        )
        assert response.status_code == 200, response.text

    body = response.json()
    assert body["status"] == "completed"
    assert [entry["input_mode"] for entry in body["transcript"]] == ["voice"] + ["text"] * (
        total - 1
    )
    # the assessor received the transcribed text, not audio
    assessed = fake_chat.calls[-1]["user"]
    assert transcriber.text in assessed
    assert company_tokens


async def test_a_typed_answer_may_declare_it_was_dictated(client, fake_chat):
    """On-device dictation posts text; the provenance still gets recorded."""
    specialist_tokens, _, match, _ = await _started_interview(client, fake_chat, prefix="va-dict")
    body = (
        await client.post(
            f"/api/v1/matches/{match['id']}/interview/answer",
            headers=auth_headers(specialist_tokens),
            json={"answer": "Dictated on the phone.", "input_mode": "voice"},
        )
    ).json()
    assert body["transcript"][0]["input_mode"] == "voice"


async def test_input_mode_defaults_to_text_for_existing_clients(client, fake_chat):
    specialist_tokens, _, match, _ = await _started_interview(client, fake_chat, prefix="va-def")
    body = (
        await client.post(
            f"/api/v1/matches/{match['id']}/interview/answer",
            headers=auth_headers(specialist_tokens),
            json={"answer": "No input_mode field at all."},
        )
    ).json()
    assert body["transcript"][0]["input_mode"] == "text"


async def test_an_invalid_input_mode_is_rejected(client, fake_chat):
    specialist_tokens, _, match, _ = await _started_interview(client, fake_chat, prefix="va-inv")
    response = await client.post(
        f"/api/v1/matches/{match['id']}/interview/answer",
        headers=auth_headers(specialist_tokens),
        json={"answer": "An answer.", "input_mode": "video"},
    )
    assert response.status_code == 422


async def test_only_the_specialist_may_answer_by_voice(client, fake_chat, transcriber):
    _, company_tokens, match, _ = await _started_interview(client, fake_chat, prefix="va-hm")
    response = await _post_audio(client, company_tokens, match["id"])
    assert response.status_code == 403
    assert transcriber.calls == []


async def test_voice_answers_stop_when_the_interview_is_complete(
    client, fake_chat, transcriber
):
    specialist_tokens, _, match, interview = await _started_interview(
        client, fake_chat, prefix="va-done"
    )
    total = interview["total_questions"]
    for index in range(total):
        if index == total - 1:
            fake_chat.responses.append(assessment_of(0.6))
        await client.post(
            f"/api/v1/matches/{match['id']}/interview/answer",
            headers=auth_headers(specialist_tokens),
            json={"answer": f"Answer {index}."},
        )

    response = await _post_audio(client, specialist_tokens, match["id"])
    assert response.status_code == 409
    assert "already completed" in response.json()["detail"]


async def test_a_transcription_failure_is_actionable_and_not_a_dead_end(client, fake_chat):
    """"Type it instead" has to be the offered way out, every time."""

    class _Failing(FakeTranscriber):
        async def transcribe(self, audio, *, filename, language=None):
            raise TranscriptionError(
                "No speech was detected in that recording. Check your microphone, or "
                "type your answer instead."
            )

    specialist_tokens, _, match, _ = await _started_interview(client, fake_chat, prefix="va-fail")
    client._transport.app.state.transcriber = _Failing()

    response = await _post_audio(client, specialist_tokens, match["id"])
    assert response.status_code == 422
    assert "type your answer instead" in response.json()["detail"]

    # the failed attempt consumed no question
    state = (
        await client.get(
            f"/api/v1/matches/{match['id']}/interview", headers=auth_headers(specialist_tokens)
        )
    ).json()
    assert state["answered_count"] == 0


async def test_the_transparency_report_records_the_input_mode(
    client, fake_chat, transcriber
):
    specialist_tokens, company_tokens, match, interview = await _started_interview(
        client, fake_chat, prefix="va-report"
    )
    total = interview["total_questions"]
    await _post_audio(client, specialist_tokens, match["id"])
    for index in range(1, total):
        if index == total - 1:
            fake_chat.responses.append(assessment_of(0.7))
        await client.post(
            f"/api/v1/matches/{match['id']}/interview/answer",
            headers=auth_headers(specialist_tokens),
            json={"answer": f"Answer {index}."},
        )

    report = (
        await client.get(
            f"/api/v1/matches/{match['id']}/transparency-report",
            headers=auth_headers(company_tokens),
        )
    ).json()["report"]
    modes = [question["answer_input_mode"] for question in report["interview"]["questions"]]
    assert modes[0] == "voice"
    assert "no audio or video is retained" in report["interview"]["modality"]
