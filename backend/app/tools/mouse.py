import asyncio
from typing import Dict, Any

try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False


async def click(target: str) -> Dict[str, Any]:
    """
    Click screen coordinates in the format "x,y".
    """

    if not PYAUTOGUI_AVAILABLE:
        return {
            "status": "error",
            "message": "pyautogui not installed.",
            "failed_command": {
                "action": "click",
                "target": target
            }
        }

    try:
        if "," not in target:
            raise ValueError("Target must be in format 'x,y'")

        parts = target.split(",")

        if len(parts) != 2:
            raise ValueError("Target must be in format 'x,y'")

        x = int(parts[0].strip()) -40
        y = int(parts[1].strip()) +100

        pyautogui.click(x, y)

        return {
            "status": "success",
            "message": f"Clicked at coordinates ({x}, {y})",
            "data": {
                "x": x,
                "y": y
            }
        }

    except ValueError as e:
        return {
            "status": "error",
            "message": str(e),
            "failed_command": {
                "action": "click",
                "target": target
            }
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to click: {str(e)}",
            "failed_command": {
                "action": "click",
                "target": target
            }
        }