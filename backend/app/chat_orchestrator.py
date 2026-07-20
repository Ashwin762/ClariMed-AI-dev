"""
backend/app/chat_orchestrator.py

Conversational orchestration for the "chat with ClariMed AI" experience --
a NEW presentation layer over the exact same safety-tested backend logic
the step-by-step wizard already uses, NOT a new, separate scoring pathway.
Every piece of actual medical logic reused here (route_to_body_part,
interpret_symptoms, interpret_symptoms_from_image, check_relevance, fuse)
is the identical, already-tested code the wizard calls -- this module only
decides WHEN to call it and HOW to phrase a natural follow-up question
when more information is still needed. It never invents its own symptom
matching or risk scoring.

DELIBERATE DESIGN CHOICE: this module duplicates a small amount of the
guidance-fetching/persistence glue that also exists in
backend/main.py's execute_screening(), rather than refactoring that
function to share this one. execute_screening() already has ~130 passing
tests behind it, built up carefully across this whole project -- touching
its internals for a refactor carries real regression risk under time
pressure, for a fairly small amount of duplicated orchestration code.
Not worth the risk.

CONVERSATION STATE: kept stateless server-side, matching the pattern
every LLM call in this codebase already uses -- the frontend holds the
full message history and sends it with each turn. No new session
infrastructure needed.

SAFETY GUARANTEE, unchanged from the wizard: a detected red flag ALWAYS
finalizes immediately (never delays emergency escalation to keep
chatting). If a conversation stays vague, route_to_body_part()'s own
existing, tested default of 'general' is accepted after a couple of
turns -- 'general' is a fully legitimate, fully-functional body part with
real KB conditions behind it, not a dead end, so there's no need for a
separate "give up and hand back to manual selection" state.
"""

import logging
from typing import List, Dict, Any, Optional

from ai.rag.body_part_router import route_to_body_part
from ai.rag.symptom_interpreter import interpret_symptoms
from ai.rag.vision_symptom_interpreter import interpret_symptoms_from_image
from ai.vision.relevance_gate import check_relevance
from ai.vision.image_analysis import extract_features, quality_check
from ai.rules.condition_engine import fuse, BODY_PART_SYMPTOMS, BODY_PART_REDFLAGS
from ai.rag.llm_client import get_llm_client, PROMPT_INJECTION_GUARD, wrap_patient_text

logger = logging.getLogger("clarimed.chat_orchestrator")

_client = get_llm_client()

_NEUTRAL_FEATURES = {
    "redness": 0.0, "yellowness": 0.0, "whiteness": 0.0,
    "variance": 0.0, "brightness": 128.0, "sharpness": 10.0,
}

# Don't chat forever -- if a body part and some symptoms still haven't
# emerged after this many patient turns, finalize with whatever's known
# (or gracefully hand back to manual body-part selection) rather than
# looping indefinitely.
_MAX_TURNS_BEFORE_FORCED_FINALIZE = 5

# Real bug found in testing: with the old threshold of 2, a single opening
# message like "fever and cough" could match 2 general symptoms and
# finalize IMMEDIATELY -- zero follow-up questions asked, ever. That's not
# how a real conversation works: a doctor (or ChatGPT) never concludes
# anything from two non-specific symptoms without asking at least one
# clarifying question first (how long, anything else, any travel, etc.).
# Two changes fix this: a higher symptom bar, AND a minimum-turn gate so
# the very first message can never finalize by symptom count alone --
# it must produce at least one real back-and-forth first. Red flags are
# completely exempt from both -- an emergency is still escalated the
# instant it's detected, never delayed for the sake of "more conversation."
_MIN_SYMPTOMS_TO_FINALIZE_EARLY = 3
_MIN_TURNS_BEFORE_SYMPTOM_COUNT_FINALIZE = 2

_DONE_SIGNAL_PHRASES = [
    "that's all", "thats all", "that is all", "nothing else",
    "no that's it", "no thats it", "that's everything", "thats everything",
    "i'm done", "im done", "that's it", "thats it",
]

_CHAT_SYSTEM_PROMPT = (
    "You are ClariMed AI's conversational screening assistant -- warm, calm, "
    "and natural, like a caring triage nurse having a real conversation, not "
    "reading a form. You are NOT diagnosing anything: never name a specific "
    "disease or condition, never suggest treatment or medication. Your only "
    "job right now is to ask ONE short, natural, specific follow-up question "
    "that helps understand the patient's symptoms better, based on the "
    "conversation so far.\n\n"
    "Prioritize whichever of these the patient hasn't already covered, in "
    "rough order of how much it actually narrows things down: how long "
    "they've had it; whether it's getting better, worse, or staying the "
    "same; any other symptoms alongside the main one (this matters most for "
    "vague complaints like 'fever' or 'cough' -- a fever's meaning changes "
    "enormously depending on what else comes with it); anything that "
    "triggers, worsens, or relieves it; and how much it's affecting daily "
    "life. Don't ask a generic 'tell me more' if you can ask something more "
    "specific than that instead -- a real intake conversation narrows down "
    "with each question, it doesn't just prompt for more words.\n\n"
    "If a photo would genuinely help and none has been shared yet, you can "
    "gently mention they're welcome to share one. Keep your reply to 1-3 "
    "short sentences -- warm and conversational, never clinical, never a "
    "checklist. "
    f"{PROMPT_INJECTION_GUARD}"
)


def _combined_user_text(messages: List[Dict[str, str]]) -> str:
    return " ".join(m.get("content", "") for m in messages if m.get("role") == "user")


def _user_signals_done(text: str) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in _DONE_SIGNAL_PHRASES)


def _generate_followup_question(messages: List[Dict[str, str]], body_part: Optional[str]) -> str:
    """
    Asks the LLM for a natural next question. Never raises -- degrades to a
    simple, still-useful canned question if no client is configured or the
    call fails, matching the graceful-degradation contract every other LLM
    call in this codebase already follows.
    """
    fallback_question = (
        "Could you tell me a bit more about what's bothering you — when it "
        "started, and anything that makes it better or worse?"
        if not body_part else
        "Thanks for that. Is there anything else about it — pain, how long "
        "it's lasted, or anything you've noticed — that might help?"
    )
    if _client is None:
        return fallback_question

    try:
        convo_text = "\n".join(f"{m.get('role')}: {m.get('content')}" for m in messages)
        response = _client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[
                {"role": "system", "content": _CHAT_SYSTEM_PROMPT},
                {"role": "user", "content": wrap_patient_text("Conversation so far", convo_text)},
            ],
            temperature=0.4,
        )
        text = response.choices[0].message.content.strip()
        return text if text else fallback_question
    except Exception as e:
        logger.warning("Follow-up question generation failed, using fallback: %s", e)
        return fallback_question


def process_chat_turn(
    messages: List[Dict[str, str]],
    body_part: Optional[str],
    image_bytes: Optional[bytes],
) -> Dict[str, Any]:
    """
    The core decision function. Returns one of:

      {"type": "question", "message": str, "body_part": Optional[str]}
        -- not enough information yet; continue the conversation. body_part
           may now be set even though we're still asking questions.

      {"type": "ready_to_finalize", "body_part": str, "symptoms": [...],
       "redflags": [...], "features": {...}, "image_provided": bool,
       "vision_other_observations": str, "relevance_warning": Optional[str]}
        -- enough information gathered (or a red flag was detected, which
           ALWAYS finalizes immediately regardless of turn count). The
           caller (the /api/chat endpoint) runs the actual fuse() +
           guidance + persistence step -- kept in main.py alongside
           execute_screening's existing, proven version of that same glue,
           not duplicated with different behavior here.
    """
    combined_text = _combined_user_text(messages)
    user_turn_count = len([m for m in messages if m.get("role") == "user"])

    # --- Determine body part, if not already known ---
    # route_to_body_part() always returns something -- it's DESIGNED to
    # default to 'general' for vague or systemic complaints (see its own
    # docstring), which is itself a fully legitimate, fully-functional body
    # part with its own real KB conditions -- not a cop-out. So there's no
    # separate "couldn't determine anything at all" state to handle here:
    # after a couple of turns to let genuine signal accumulate, whatever
    # route_to_body_part settles on (including 'general') is accepted and
    # the conversation proceeds normally from there.
    if not body_part:
        guessed = route_to_body_part(combined_text)
        if guessed != "general" or user_turn_count >= 2:
            body_part = guessed

    if not body_part:
        return {"type": "question", "message": _generate_followup_question(messages, None), "body_part": None}

    # --- Extract symptoms and red flags from the conversation so far,
    #     using the EXACT same closed-list-safe function the wizard uses ---
    known_symptoms = BODY_PART_SYMPTOMS.get(body_part, [])
    known_redflags = BODY_PART_REDFLAGS.get(body_part, [])
    text_symptoms = interpret_symptoms(combined_text, known_symptoms)
    redflags = interpret_symptoms(combined_text, known_redflags)
    symptoms = list(text_symptoms)

    # --- Image, if one was shared this turn ---
    features = _NEUTRAL_FEATURES
    image_provided = False
    vision_detected_symptoms: List[str] = []
    vision_other_observations = ""
    relevance_warning = None

    if image_bytes:
        try:
            features = extract_features(image_bytes)
            q = quality_check(features)
            if q["passed"]:
                image_provided = True
                relevance = check_relevance(image_bytes, body_part)
                if relevance["checked"] and relevance["relevant"] is False:
                    relevance_warning = relevance["warning"]
                    logger.info(
                        "Chat: skipping vision-based symptom detection for %s -- "
                        "photo flagged as not relevant (confidence=%s)",
                        body_part, relevance["confidence"],
                    )
                else:
                    vision_result = interpret_symptoms_from_image(image_bytes, body_part, known_symptoms)
                    vision_other_observations = vision_result["other_observations"]
                    vision_detected_symptoms = vision_result["matched_symptoms"]
                    for s in vision_detected_symptoms:
                        if s not in symptoms:
                            symptoms.append(s)
            else:
                logger.info("Chat: image quality check failed, ignoring photo: %s", q["issues"])
        except Exception as e:
            logger.warning("Chat: image processing failed, continuing without it: %s", e)

    # --- Decide whether to finalize ---
    # Red flags NEVER wait for more conversation -- same principle as
    # everywhere else in this codebase: a possible emergency is escalated
    # the moment it's detected, not once the chat "feels" complete.
    should_finalize = False
    if redflags:
        should_finalize = True
    elif len(symptoms) >= _MIN_SYMPTOMS_TO_FINALIZE_EARLY and user_turn_count >= _MIN_TURNS_BEFORE_SYMPTOM_COUNT_FINALIZE:
        should_finalize = True
    elif user_turn_count >= _MAX_TURNS_BEFORE_FORCED_FINALIZE:
        should_finalize = True
    elif _user_signals_done(combined_text):
        should_finalize = True

    if should_finalize:
        return {
            "type": "ready_to_finalize",
            "body_part": body_part,
            "symptoms": symptoms,
            "text_interpreted_symptoms": text_symptoms,
            "vision_detected_symptoms": vision_detected_symptoms,
            "redflags": redflags,
            "features": features,
            "image_provided": image_provided,
            "vision_other_observations": vision_other_observations,
            "relevance_warning": relevance_warning,
        }

    return {
        "type": "question",
        "message": _generate_followup_question(messages, body_part),
        "body_part": body_part,
    }