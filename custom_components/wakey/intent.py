"""Voice snooze/cancel for Wakey via Home Assistant's Assist pipeline.

Deliberately global, not scoped to a specific alarm or satellite: any Assist
satellite in the house can snooze or dismiss whatever alarm is currently
ringing, regardless of whose alarm it is or which room it's in — the same way
a smart speaker's own "stop"/"snooze" isn't tied to which device set the
alarm off.
"""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

INTENT_SNOOZE = "WakeySnooze"
INTENT_DISMISS = "WakeyDismiss"

# Seed every shipped language: the Assist pipeline language can differ from
# hass.config.language, and a household can use several pipelines.
# HA may resolve German regional pipelines to de-CH instead of de.
_SENTENCE_LANGUAGES = {"en": "en", "de": "de", "de-CH": "de"}


def _get_data(hass: HomeAssistant):
    return next(iter(hass.data.get(DOMAIN, {}).values()), None)


class _WakeySnoozeIntent(intent.IntentHandler):
    intent_type = INTENT_SNOOZE
    description = "Snooze whatever Wakey alarm is currently ringing"

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        if (data := _get_data(intent_obj.hass)) is not None:
            await data.player.async_snooze_all()
        response = intent_obj.create_response()
        response.async_set_speech("")
        return response


class _WakeyDismissIntent(intent.IntentHandler):
    intent_type = INTENT_DISMISS
    description = "Dismiss whatever Wakey alarm is currently ringing"

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        if (data := _get_data(intent_obj.hass)) is not None:
            await data.player.async_dismiss_all()
        response = intent_obj.create_response()
        response.async_set_speech("")
        return response


async def async_setup_intents(hass: HomeAssistant) -> None:
    """Register the snooze/dismiss intents and seed their trigger sentences.

    Idempotent, like _async_register_services: Home Assistant may run entry
    setup more than once in a boot, and re-registering an intent logs an
    "is being overwritten" warning.
    """
    registered = {handler.intent_type for handler in intent.async_get(hass)}
    if INTENT_SNOOZE not in registered:
        intent.async_register(hass, _WakeySnoozeIntent())
    if INTENT_DISMISS not in registered:
        intent.async_register(hass, _WakeyDismissIntent())

    def _write_sentences() -> bool:
        changed = False
        for language, corpus in _SENTENCE_LANGUAGES.items():
            source = Path(__file__).parent / "sentences" / f"{corpus}.yaml"
            path = Path(hass.config.path("custom_sentences", language, f"{DOMAIN}.yaml"))
            content = source.read_text(encoding="utf-8")
            content = content.replace(f'language: "{corpus}"', f'language: "{language}"', 1)
            path.parent.mkdir(parents=True, exist_ok=True)
            # Only manage our own file. User phrases belong in separate files.
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                path.write_text(content, encoding="utf-8")
                changed = True
        return changed

    changed = await hass.async_add_executor_job(_write_sentences)
    # The conversation agent may already have cached its sentence corpus.
    if changed and hass.services.has_service("conversation", "reload"):
        await hass.services.async_call("conversation", "reload", {}, blocking=True)


def async_remove_intents(hass: HomeAssistant) -> None:
    """Unregister the snooze/dismiss intents. The sentence file is left in place."""
    intent.async_remove(hass, INTENT_SNOOZE)
    intent.async_remove(hass, INTENT_DISMISS)
