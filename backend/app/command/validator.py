from .schema import CommandPlan
from pydantic import ValidationError

class InvalidCommandPlanError(Exception):
    """Raised when Gemini's output fails schema validation."""
    pass

def validate_gemini_output(raw_json: dict) -> CommandPlan:
    """
    Validates Gemini's raw JSON output against CommandPlan schema.

    Args:
        raw_json: Dictionary parsed from Gemini's response string

    Returns:
        Validated CommandPlan object

    Raises:
        InvalidCommandPlanError: If output doesn't match schema
    """
    try:
        # Pydantic validates:
        # 1. Must have "commands" key
        # 2. Commands must be list
        # 3. Each command must have valid ActionType
        # 4. Each target must be string
        # 5. At least one command (min_items=1)
        return CommandPlan(**raw_json)
    except ValidationError as e:
        # Format error for user-friendly message (no internal details)
          error_msgs = []
          for error in e.errors():
              loc = " -> ".join(str(loc_part) for loc_part in error["loc"])
              msg = error["msg"]
              error_msgs.append(f"Field '{loc}': {msg}")

          raise InvalidCommandPlanError(
            f"Gemini output invalid. Errors: {'; '.join(error_msgs)}. "
            f"Expected format: {{'commands': [{{'action': '<{','.join([a.value for a in ActionType])}>', "
            f"'target': '<string>', 'value': '<string|optional>'}}]}}"
            f"Note: 'value' is optional and only used for browser actions."
        )
    except Exception as e:
        # Catch any other unexpected errors (e.g., not a dict)
        raise InvalidCommandPlanError(
            f"Gemini output must be JSON object. Error: {str(e)}"
        )