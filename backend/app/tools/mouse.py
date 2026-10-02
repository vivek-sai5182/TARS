import asyncio
from typing import Dict, Any
try:
    from pywinauto import Application
    from pywinauto.findwindows import ElementNotFoundError
    PYWINAUTO_AVAILABLE = True
except ImportError:
    PYWINAUTO_AVAILABLE = False

async def click(target: str) -> Dict[str, Any]:
    """
    Clicks at the specified coordinates or attempts to find and click an element by text.
    For simplicity in demo, we treat target as coordinates in format "x,y" (e.g., "100,200").
    For future screen-aware features, this could be extended to use OCR or UI Automation.
    """
    if not PYWINAUTO_AVAILABLE:
        return {
            "status": "error",
            "message": "pywinauto not installed. Install with: pip install pywinauto",
            "failed_command": {"action": "click", "target": target}
        }

    try:
        # Parse target as coordinates (x,y)
        # In a more advanced version, we could use target as a label to search for UI elements
        # But for MVP demo, we assume target is "x,y"
        if ',' in target:
            parts = target.split(',')
            if len(parts) != 2:
                raise ValueError("Target must be in format 'x,y'")
            x = int(parts[0].strip())
            y = int(parts[1].strip())
        else:
            # If not coordinates, treat as a single number (x) and assume y=0?
            # Better to require coordinates for clarity.
            raise ValueError("Target must be in format 'x,y' (e.g., '100,200')")

        # Get the currently active window
        app = Application().connect(active_only=True, timeout=5)
        window = app.window(active_only=True)

        # Move mouse to coordinates and click
        # Note: pywinauto's mouse.move_coords() and click() work relative to the window
        # We need to get the window's rectangle to convert screen coordinates to client coordinates
        window_rect = window.rectangle()
        # Convert screen coordinates to client coordinates (relative to window top-left)
        client_x = x - window_rect.left
        client_y = y - window_rect.top

        # Move and click
        window.mouse.move_coords((client_x, client_y))
        window.click_input()  # Click at current mouse position

        return {
            "status": "success",
            "message": f"Clicked at coordinates ({x}, {y})",
            "data": {"x": x, "y": y, "client_x": client_x, "client_y": client_y}
        }

    except ValueError as e:
        return {
            "status": "error",
            "message": f"Invalid target format: {str(e)}. Use 'x,y' (e.g., '100,200')",
            "failed_command": {"action": "click", "target": target}
        }
    except ElementNotFoundError:
        return {
            "status": "error",
            "message": "Could not find active window. Make sure an application is focused.",
            "failed_command": {"action": "click", "target": target}
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to click: {str(e)}",
            "failed_command": {"action": "click", "target": target}
        }