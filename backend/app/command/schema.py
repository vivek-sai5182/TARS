from enum import Enum
from pydantic import BaseModel, Field
from typing import List,Optional

class ActionType(str, Enum):
    """
    LOCKED DOWN FOR MVP DEMO.
    - Gemini MUST only output these exact strings.
    - Backend tools MUST implement exactly these actions.
    - CHANGING THIS BREAKS VALIDATION/DISPATCHER.
    """
    OPENAPPLICATION = "open_application"   # Launch Brave (or any Win32 app)
    OPENWEBSITE = "open_website"           # Navigate to URL OR search term (smart resolution in browser tool)
    CLOSEAPPLICATION = "close_application" # Close focused app (useful for demo cleanup)
    SEARCH = "search"                      # Perform search (distinct from open_website for clarity)
    TYPE = "type"                          # Type text into focused field
    CLICK = "click"                        # Mouse click at coordinates/element
    PRESSKEY = "press_key"                 # Press key/combo (Enter, Ctrl+C, etc.)
    WAIT = "wait"                          # Pause execution (seconds)
    BROWSER_CLICK = "browser_click"
    BROWSER_TYPE = "browser_type"
    BROWSER_PRESS = "browser_press"
    LIST_ITEM = "list_item"

    # FUTURE-PROOFING (DO NOT USE IN GEMINI PROMPTS FOR MVP):
    # These are RESERVED for Phase 2+ but SAFE to keep in enum now
    # FINDELEMENT = "find_element"          # Screen-aware element lookup (Phase 3)
    # REQUESTCLARIFICATION = "request_clarification" # For ambiguous turns (Phase 2)
    # GETUISTATE = "get_ui_state"           # Debug-only (never expose to Gemini)

class Command(BaseModel):
    """Single command unit. Gemini outputs LIST of these."""
    action: ActionType = Field(
        ...,
        description="MUST be from ActionType enum. Gemini sees ONLY these strings."
    )
    target: str = Field(
        ...,
        description="Always a string. Examples: 'Brave', 'youtube.com', 'hello world', '5'"
    )
    value: Optional[str] = Field(
        None,
        description="Optional value for browser actions (e.g., text to type). Desktop actions ignore this field."
    )

class CommandPlan(BaseModel):
    """THE ONLY VALID GEMINI OUTPUT. Must have ≥1 command."""
    commands: List[Command] = Field(
        ...,
        min_items=1,
        description="Gemini MUST output JSON matching this structure. "
                    "Example: {'commands': [{'action': 'open_application', 'target': 'Brave'}]}"
    )
    