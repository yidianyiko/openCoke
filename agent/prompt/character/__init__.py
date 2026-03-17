# -*- coding: utf-8 -*-
"""
Character System Prompt Module

Each character has its own prompt file containing its system prompt.
This allows:
- Git version control
- Easy prompt fine-tuning and iteration
- Consistent management with other prompt files
"""

from agent.prompt.character.coke_prompt import COKE_STATUS, COKE_SYSTEM_PROMPT

# Character configuration registry
# key: character name (matches the `name` field in the database)
# value: (system prompt, status config)
CHARACTER_PROMPTS = {
    "qiaoyun": {
        "system_prompt": COKE_SYSTEM_PROMPT,
        "status": COKE_STATUS,
    },
    # To add new characters in the future, register them here:
    # "new_character": {
    #     "system_prompt": NEW_CHARACTER_SYSTEM_PROMPT,
    #     "status": NEW_CHARACTER_STATUS,
    # },
}


def get_character_prompt(character_name: str) -> str | None:
    """
    Get the system prompt for a character.

    Args:
        character_name: Character name

    Returns:
        System prompt string, or None if the character does not exist
    """
    config = CHARACTER_PROMPTS.get(character_name.lower())
    if config:
        return config.get("system_prompt")
    return None


def get_character_status(character_name: str) -> dict | None:
    """
    Get the status configuration for a character.

    Args:
        character_name: Character name

    Returns:
        Status configuration dictionary, or None if the character does not exist
    """
    config = CHARACTER_PROMPTS.get(character_name.lower())
    if config:
        return config.get("status")
    return None
