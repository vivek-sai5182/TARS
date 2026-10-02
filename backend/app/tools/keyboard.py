import asyncio
from typing import Dict, Any
try:
    from pywinauto import Application
    from pywinauto.findwindows import ElementNotFoundError
    PYWINAUTO_AVAILABLE = True
except ImportError:
    PYWINAUTO_AVAILABLE = False

async def type_text(target: str) -> Dict[str, Any]:
    """
    Types the specified text into the currently focused input field.
    Uses pywinauto to send keystrokes to the active window.
    """
    if not PYWINAUTO_AVAILABLE:
        return {
            "status": "error",
            "message": "pywinauto not installed. Install with: pip install pywinauto",
            "failed_command": {"action": "type", "target": target}
        }

    try:
        # Get the currently active window
        app = Application().connect(active_only=True, timeout=5)
        window = app.window(active_only=True)

        # Type the text
        window.type_keys(target, with_spaces=True, pause=0.1)

        return {
            "status": "success",
            "message": f"Typed: '{target}'",
            "data": {"text": target}
        }

    except ElementNotFoundError:
        return {
            "status": "error",
            "message": "Could not find active window. Make sure an application is focused.",
            "failed_command": {"action": "type", "target": target}
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to type text: {str(e)}",
            "failed_command": {"action": "type", "target": target}
        }

async def press_key(target: str) -> Dict[str, Any]:
    """
    Presses a key or key combination (e.g., "enter", "ctrl+c", "alt+tab").
    """
    if not PYWINAUTO_AVAILABLE:
        return {
            "status": "error",
            "message": "pywinauto not installed. Install with: pip install pywinauto",
            "failed_command": {"action": "press_key", "target": target}
        }

    try:
        # Get the currently active window
        app = Application().connect(active_only=True, timeout=5)
        window = app.window(active_only=True)

        # Parse key combinations
        keys = target.lower().split('+')
        formatted_keys = []
        for key in keys:
            key = key.strip()
            if key in ['ctrl', 'control']:
                formatted_keys.append('^')
            elif key in ['alt', 'menu']:
                formatted_keys.append('%')
            elif key in ['shift']:
                formatted_keys.append('+')
            elif key == 'enter':
                formatted_keys.append('{ENTER}')
            elif key == 'tab':
                formatted_keys.append('{TAB}')
            elif key == 'escape':
                formatted_keys.append('{ESC}')
            elif key == 'space':
                formatted_keys.append('{SPACE}')
            elif key == 'up':
                formatted_keys.append('{UP}')
            elif key == 'down':
                formatted_keys.append('{DOWN}')
            elif key == 'left':
                formatted_keys.append('{LEFT}')
            elif key == 'right':
                formatted_keys.append('{RIGHT}')
            else:
                # Single character
                formatted_keys.append(key)

        # Send the key combination
        key_string = ''.join(formatted_keys)
        window.type_keys(key_string)

        return {
            "status": "success",
            "message": f"Pressed keys: {target}",
            "data": {"keys": target}
        }

    except ElementNotFoundError:
        return {
            "status": "error",
            "message": "Could not find active window. Make sure an application is focused.",
            "failed_command": {"action": "press_key", "target": target}
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to press keys: {str(e)}",
            "failed_command": {"action": "press_key", "target": target}
        }