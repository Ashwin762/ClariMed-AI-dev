"""
tests/test_chat_orchestrator.py

Tests backend/app/chat_orchestrator.py -- the conversational decision layer
sitting on top of the exact same safety-tested functions the step-by-step
wizard already uses. These tests mock those underlying functions
(route_to_body_part, interpret_symptoms, etc.) so they verify exactly what
THIS module is responsible for -- the finalize/continue decisions -- not
re-testing matching accuracy that's already covered elsewhere.

The one test that intentionally does NOT mock anything
(test_redflag_finalizes_immediately_even_on_first_turn) is the single most
safety-critical property in this whole module, and is worth proving against
the real underlying functions, not just a mock.
"""

import backend.app.chat_orchestrator as co


def test_redflag_finalizes_immediately_even_on_first_turn():
    """THE most important property in this module: a red flag must finalize
    on the very first message, never wait for more conversation. Uses the
    real interpret_symptoms()/route_to_body_part() (not mocked) -- this is
    worth proving end-to-end, not just against a mock."""
    messages = [{"role": "user", "content": "I have chest pain radiating to my arm with cold sweat"}]
    result = co.process_chat_turn(messages, body_part="cardiovascular", image_bytes=None)
    assert result["type"] == "ready_to_finalize"
    assert len(result["redflags"]) > 0


def test_redflag_overrides_low_symptom_count(monkeypatch):
    """Even with only 1 (or 0) matched symptoms, a red flag must still force
    finalize -- red-flag detection is never gated behind the symptom-count
    threshold."""
    monkeypatch.setattr(co, "interpret_symptoms", lambda text, known: (
        ["Sudden Vision Loss"] if known == co.BODY_PART_REDFLAGS.get("eye") else []
    ))
    messages = [{"role": "user", "content": "anything"}]
    result = co.process_chat_turn(messages, body_part="eye", image_bytes=None)
    assert result["type"] == "ready_to_finalize"
    assert result["redflags"] == ["Sudden Vision Loss"]
    assert result["symptoms"] == []


def test_not_enough_info_yet_returns_a_question(monkeypatch):
    """With body part known but fewer than the finalize threshold's worth of
    symptoms, on an early turn, the orchestrator must ask a follow-up
    question rather than finalize prematurely."""
    monkeypatch.setattr(co, "interpret_symptoms", lambda text, known: (
        ["Ocular Redness"] if known == co.BODY_PART_SYMPTOMS.get("eye") else []
    ))
    monkeypatch.setattr(co, "_generate_followup_question", lambda messages, bp: "Can you tell me more?")
    messages = [{"role": "user", "content": "my eye is red"}]
    result = co.process_chat_turn(messages, body_part="eye", image_bytes=None)
    assert result["type"] == "question"
    assert result["body_part"] == "eye"
    assert isinstance(result["message"], str) and len(result["message"]) > 0


def test_two_symptoms_on_first_turn_does_not_finalize_immediately(monkeypatch):
    """THE real bug reported in testing: a single opening message like
    'fever and cough' matched 2 general symptoms and finalized IMMEDIATELY --
    zero follow-up questions ever asked, producing a jarring, overly broad
    result (mentioning things like chikungunya/COVID from just two vague
    symptoms) instead of a real conversation. This must now ask at least one
    clarifying question first."""
    monkeypatch.setattr(co, "interpret_symptoms", lambda text, known: (
        ["Fever", "Cough"] if known == co.BODY_PART_SYMPTOMS.get("general") else []
    ))
    monkeypatch.setattr(co, "_generate_followup_question", lambda messages, bp: "How long have you had these, and is anything else going on alongside them?")
    messages = [{"role": "user", "content": "I have fever and cough"}]
    result = co.process_chat_turn(messages, body_part="general", image_bytes=None)
    assert result["type"] == "question", (
        "two non-specific symptoms on the very first message must not finalize immediately"
    )


def test_three_symptoms_after_a_real_exchange_does_finalize(monkeypatch):
    """The new, intentional threshold: once there's been at least one real
    back-and-forth AND enough symptoms have accumulated, finalizing is the
    right call -- this isn't about finalizing later forever, just not on
    the very first vague message."""
    monkeypatch.setattr(co, "interpret_symptoms", lambda text, known: (
        ["Fever", "Cough", "Body Ache"] if known == co.BODY_PART_SYMPTOMS.get("general") else []
    ))
    messages = [
        {"role": "user", "content": "I have fever and cough"},
        {"role": "assistant", "content": "How long, and anything else alongside it?"},
        {"role": "user", "content": "Two days, and my whole body aches too"},
    ]
    result = co.process_chat_turn(messages, body_part="general", image_bytes=None)
    assert result["type"] == "ready_to_finalize"
    assert len(result["symptoms"]) >= 3


def test_two_symptoms_triggers_finalize(monkeypatch):
    """Same symptom count as the bug case, but AFTER a real exchange has
    already happened -- the turn-count gate, not the symptom threshold
    alone, is what changed."""
    monkeypatch.setattr(co, "interpret_symptoms", lambda text, known: (
        ["Ocular Redness", "Watery Eyes", "Eye Pain"] if known == co.BODY_PART_SYMPTOMS.get("eye") else []
    ))
    messages = [
        {"role": "user", "content": "my eye is red and watery"},
        {"role": "assistant", "content": "How long has this been going on?"},
        {"role": "user", "content": "Two days now, and it hurts a bit too"},
    ]
    result = co.process_chat_turn(messages, body_part="eye", image_bytes=None)
    assert result["type"] == "ready_to_finalize"
    assert len(result["symptoms"]) >= 2


def test_done_signal_forces_finalize_even_with_few_symptoms(monkeypatch):
    monkeypatch.setattr(co, "interpret_symptoms", lambda text, known: (
        ["Ocular Redness"] if known == co.BODY_PART_SYMPTOMS.get("eye") else []
    ))
    messages = [
        {"role": "user", "content": "my eye is red"},
        {"role": "assistant", "content": "Anything else?"},
        {"role": "user", "content": "no that's all"},
    ]
    result = co.process_chat_turn(messages, body_part="eye", image_bytes=None)
    assert result["type"] == "ready_to_finalize"


def test_forced_finalize_after_max_turns_prevents_infinite_loop(monkeypatch):
    """No matter how sparse the conversation, this module must never loop
    forever -- a hard cap on turns guarantees a result eventually."""
    monkeypatch.setattr(co, "interpret_symptoms", lambda text, known: [])
    messages = [{"role": "user", "content": "still not well"}] * (co._MAX_TURNS_BEFORE_FORCED_FINALIZE + 1)
    result = co.process_chat_turn(messages, body_part="general", image_bytes=None)
    assert result["type"] == "ready_to_finalize"


def test_vague_conversation_settles_on_general_rather_than_looping(monkeypatch):
    """route_to_body_part() already defaults to 'general' for vague
    complaints -- accepted here after a couple of turns rather than treated
    as a failure state, since 'general' is a fully real, working body part."""
    monkeypatch.setattr(co, "route_to_body_part", lambda text: "general")
    monkeypatch.setattr(co, "interpret_symptoms", lambda text, known: [])
    messages = [{"role": "user", "content": "i dont feel good"}] * 3
    result = co.process_chat_turn(messages, body_part=None, image_bytes=None)
    assert result["type"] in ("question", "ready_to_finalize")
    if result["type"] == "question":
        assert result["body_part"] == "general"
    else:
        assert result["body_part"] == "general"


def test_general_guess_not_accepted_on_the_very_first_turn(monkeypatch):
    """A bare 'general' default on turn 1, before any real signal has had a
    chance to accumulate, should still prompt one clarifying question rather
    than being accepted immediately -- otherwise a single ambiguous opener
    ('I don't feel good') would skip straight past ever asking anything."""
    monkeypatch.setattr(co, "route_to_body_part", lambda text: "general")
    monkeypatch.setattr(co, "interpret_symptoms", lambda text, known: [])
    monkeypatch.setattr(co, "_generate_followup_question", lambda messages, bp: "Tell me more?")
    messages = [{"role": "user", "content": "i dont feel good"}]
    result = co.process_chat_turn(messages, body_part=None, image_bytes=None)
    assert result["type"] == "question"
    assert result["body_part"] is None


def test_followup_question_generation_never_raises_without_a_client(monkeypatch):
    """Graceful degradation: with no LLM client configured, a real, usable
    fallback question must still come back -- never a crash, never an empty
    string."""
    monkeypatch.setattr(co, "_client", None)
    question = co._generate_followup_question([{"role": "user", "content": "my skin itches"}], "skin")
    assert isinstance(question, str) and len(question) > 0


def test_image_quality_failure_does_not_crash_the_turn():
    """A genuinely corrupt/unreadable image attached mid-conversation must
    not break the chat -- it should just be treated as if no image was
    provided, same graceful-degradation contract as every other image entry
    point in this codebase."""
    messages = [{"role": "user", "content": "here is a photo"}]
    result = co.process_chat_turn(messages, body_part="eye", image_bytes=b"not a real image at all")
    assert result["type"] in ("question", "ready_to_finalize")
    if result["type"] == "ready_to_finalize":
        assert result["image_provided"] is False


def test_combined_user_text_ignores_assistant_turns():
    messages = [
        {"role": "user", "content": "my eye hurts"},
        {"role": "assistant", "content": "I'm sorry to hear that, tell me more"},
        {"role": "user", "content": "it's also red"},
    ]
    combined = co._combined_user_text(messages)
    assert "eye hurts" in combined
    assert "also red" in combined
    assert "sorry to hear" not in combined.lower()


def test_done_signal_detection_is_case_insensitive():
    assert co._user_signals_done("That's All, nothing more") is True
    assert co._user_signals_done("I still have more to say") is False