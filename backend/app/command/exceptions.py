class InvalidCommandPlanError(Exception):
    """Raised when Gemini's output fails schema validation."""
    pass

class DispatchError(Exception):
    """Raised when command dispatch fails."""
    pass