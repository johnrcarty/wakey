"""Voice commands must match through HA's conversation agent in each language."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.components import conversation
from homeassistant.core import Context
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.wakey.const import DOMAIN
from custom_components.wakey.intent import async_setup_intents


@pytest.fixture
async def sentence_config(hass, tmp_path):
    hass.config.config_dir = str(tmp_path)
    (tmp_path / "configuration.yaml").write_text("conversation: {}\n", encoding="utf-8")
    # Deliberately different from the language used by the Assist pipeline.
    hass.config.language = "fr"
    assert await async_setup_component(hass, "homeassistant", {})
    player = AsyncMock()
    hass.data[DOMAIN] = {"test": SimpleNamespace(player=player)}
    return tmp_path, player


@pytest.mark.parametrize(("language", "phrase", "method"), [
    ("en", "snooze", "async_snooze_all"),
    ("en", "stop the alarm", "async_dismiss_all"),
    ("de", "schlummern", "async_snooze_all"),
    ("de", "Wecker pausieren", "async_snooze_all"),
    ("de", "Wecker stoppen", "async_dismiss_all"),
    ("de", "Stoppe den Alarm", "async_dismiss_all"),
    ("de-AT", "Wecker beenden", "async_dismiss_all"),
    ("de-CH", "schlummern", "async_snooze_all"),
])
async def test_conversation_matches_wakey(hass, sentence_config, language, phrase, method):
    _, player = sentence_config
    await async_setup_intents(hass)
    assert await async_setup_component(hass, "conversation", {})
    await conversation.async_converse(hass, phrase, None, Context(), language=language)
    getattr(player, method).assert_awaited_once_with()


async def test_setup_preserves_user_files_and_unchanged_managed_files(hass, sentence_config):
    config, _ = sentence_config
    user_file = config / "custom_sentences" / "de" / "personal.yaml"
    user_file.parent.mkdir(parents=True)
    user_file.write_text("# User-owned phrases\n", encoding="utf-8")
    reloads = async_mock_service(hass, "conversation", "reload")
    await async_setup_intents(hass)
    managed = [config / "custom_sentences" / lang / "wakey.yaml" for lang in ("en", "de", "de-CH")]
    mtimes = [p.stat().st_mtime_ns for p in managed]
    await async_setup_intents(hass)
    assert [p.stat().st_mtime_ns for p in managed] == mtimes
    assert user_file.read_text() == "# User-owned phrases\n"
    assert len(reloads) == 1


async def test_setup_reloads_previously_cached_sentences(hass, sentence_config):
    _, player = sentence_config
    assert await async_setup_component(hass, "conversation", {})
    await conversation.async_converse(hass, "schlummern", None, Context(), language="de")
    player.async_snooze_all.assert_not_awaited()
    await async_setup_intents(hass)
    await conversation.async_converse(hass, "schlummern", None, Context(), language="de")
    player.async_snooze_all.assert_awaited_once_with()
