from .schema import Command, ActionType
from .exceptions import DispatchError
from ..tools import applications, browser, keyboard, mouse
from ..session.tracker import session_state

async def dispatch_command(command: Command) -> dict:
    """
    Dispatches a single command to the appropriate tool and updates session state.

    Args:
        command: Validated Command object (action from ActionType enum, target string)

    Returns:
        Dictionary with execution result: {"status": "success"/"error", "data": ..., "message": "..."}
    """
    try:
        # Map ActionType to the corresponding tool function
        tool_map = {
            ActionType.OPENAPPLICATION: applications.open,
            ActionType.OPENWEBSITE: browser.open,
            ActionType.CLOSEAPPLICATION: applications.close,
            ActionType.SEARCH: browser.search,
            ActionType.TYPE: keyboard.type_text,
            ActionType.CLICK: mouse.click,
            ActionType.PRESSKEY: keyboard.press_key,
            ActionType.WAIT: browser.wait,
            # Note: Future actions (FINDELEMENT, etc.) will be added here when implemented
        }

        tool_func = tool_map.get(command.action)
        if not tool_func:
            return {
                "status": "error",
                "message": f"Unsupported action: {command.action.value}",
                "failed_command": command.dict()
            }

        # Execute the tool function (all tools are async)
        result = await tool_func(command.target)

        if result.get("status") == "success":
            await session_state.update_after_command(command, result)

        return result

    except Exception as e:
        # Don't update session state on failure
        return {
            "status": "error",
            "message": str(e),
            "failed_command": command.dict()
        }

async def dispatch_plan(plan) -> list:
    """
    Dispatches a sequence of commands (a CommandPlan) and returns results for each.

    Args:
        plan: Validated CommandPlan object (list of Command objects)

    Returns:
        List of result dictionaries (one per command, in order)
        Stops execution on first error (configurable - currently stops on error)
    """
    results = []
    for command in plan.commands:
        result = await dispatch_command(command)
        results.append(result)
        # Stop execution on first error (for safety in demo)
        if result.get("status") == "error":
            break
    return results