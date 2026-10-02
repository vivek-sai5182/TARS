import win32gui
import win32process
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

@dataclass
class AppInfo:
    """Information about a tracked application window."""
    name: str          # Process name (e.g., "Chrome")
    pid: int           # Process ID
    hwnd: int          # Window handle
    title: str         # Window title (e.g., "YouTube - Google Chrome")
    last_active: datetime

class SessionState:
    """
    Manages session state for turn-by-turn awareness.
    Pure backend state - zero AI involvement.
    Tracks: active applications, browser context, UI cache, action history.
    """

    def __init__(self):
        # Map of window handle (hwnd) to AppInfo
        self.active_applications: Dict[int, AppInfo] = {}
        #Currently focusing window
        self.focused_window: Optional[int] = None
        # Last known browser URL (for context in search/open_website)
        self.last_browser_url: str = ""
        # Cached UI elements: label -> (x, y) coordinates
        self.ui_elements: Dict[str, Tuple[int, int]] = {}
        # History of executed commands (for anaphora resolution: "do that again")
        self.action_history: List[dict] = []  # Each item: {"command": dict, "result": dict, "timestamp": datetime}

    def get_context_summary(self) -> str:
        """
        Generates a text summary of current session state for Gemini prompts.
        Called by gemini_planner.py to enrich prompts with context.
        Never sends raw screenshots, PII, or page content - only anonymized summaries.
        """
        # Get current foreground window (what user is actively interacting with)
        fg_hwnd = win32gui.GetForegroundWindow()
        fg_info = self._get_window_info(fg_hwnd) if fg_hwnd else None

        # Update active applications list with current foreground window
        if fg_hwnd and fg_hwnd not in self.active_applications:
            self.active_applications[fg_hwnd] = fg_info
        elif fg_hwnd and fg_hwnd in self.active_applications:
            # Update last_active and title (title can change)
            existing = self.active_applications[fg_hwnd]
            existing.last_active = fg_info.last_active if fg_info else existing.last_active
            existing.title = fg_info.title if fg_info else existing.title

        # Build summary lines
        lines = []

        # Active applications (excluding minimized/hidden if needed)
        if self.active_applications:
            app_lines = []
            for hwnd, app in self.active_applications.items():
                # Only show if window is visible (optional - show all for simplicity)
                app_lines.append(f"{app.name} ({app.title})")
            lines.append(f"Active applications: {', '.join(app_lines)}")
        else:
            lines.append("Active applications: None")

        # Focused window
        if fg_info:
            lines.append(f"Focused window: {fg_info.name} ({fg_info.title})")
        else:
            lines.append("Focused window: None")

        # Browser context
        lines.append(f"Last browser URL: {self.last_browser_url or 'None'}")

        # Recent actions (last 5 for brevity)
        recent = self.action_history[-5:] if len(self.action_history) > 5 else self.action_history
        if recent:
            action_descs = [
                f"{item['command'].get('action', '?')} → {item['command'].get('target', '?')}"
                for item in recent
            ]
            lines.append(f"Recent actions: {len(self.action_history)} total (last 5: {', '.join(action_descs)})")
        else:
            lines.append("Recent actions: None")

        return "\n".join(lines)

    async def update_after_command(self, command, result: dict):
        """
        Updates session state after a command executes successfully.
        Called by dispatcher.py after each tool execution.
        """
        # Always update action history
        self.action_history.append({
            "command": command.dict() if hasattr(command, 'dict') else command,
            "result": result,
            "timestamp": datetime.now()
        })
        # Keep history bounded (last 20 actions)
        if len(self.action_history) > 20:
            self.action_history = self.action_history[-20:]

        # Command-specific state updates
        if hasattr(command, 'action'):
            action = command.action
            # Handle application launching
            if action == "open_application" and result.get("status") == "success":
                # Tool should return hwnd in result data for new window
                hwnd = result.get("data", {}).get("hwnd")

                if hwnd:
                    await self._register_new_application(hwnd, command.target, result)

                    # Remember this as the currently focused window
                    self.focused_window = hwnd

            # Handle browser navigation/search
            elif action in ["open_website", "search"] and result.get("status") == "success":
                # Update last browser URL from result
                url = result.get("data", {}).get("url")
                if url:
                    self.last_browser_url = url
                # Remember the browser window used
                hwnd = result.get("data", {}).get("hwnd")
                if hwnd:
                    self.focused_window = hwnd
                # Cache UI elements if provided by tool (for future screen-aware features)
                elements = result.get("data", {}).get("ui_elements", {})
                if elements:
                    self.ui_elements.update(elements)

            # Handle application closing
            elif action == "close_application" and result.get("status") == "success":
                # Remove closed application from tracking (by hwnd if provided)
                hwnd = result.get("data", {}).get("hwnd")
                if hwnd and hwnd in self.active_applications:
                    del self.active_applications[hwnd]

    async def _register_new_application(self, hwnd: int, app_name: str, result: dict):
        """Register a newly launched application in session state."""
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            title = win32gui.GetWindowText(hwnd)
            self.active_applications[hwnd] = AppInfo(
                name=app_name,
                pid=pid,
                hwnd=hwnd,
                title=title,
                last_active=datetime.now()
            )
        except Exception:
            # Best effort - if we can't get info, still track by hwnd with minimal data
            self.active_applications[hwnd] = AppInfo(
                name=app_name,
                pid=0,
                hwnd=hwnd,
                title="Unknown",
                last_active=datetime.now()
            )

    def _get_window_info(self, hwnd: int) -> Optional[AppInfo]:
        """Get information for a window handle, or None if invalid."""
        try:
            if not win32gui.IsWindow(hwnd):
                return None
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            title = win32gui.GetWindowText(hwnd)
            # Get process name (requires opening handle - simplified for demo)
            name = "Unknown"
            try:
                import psutil
                proc = psutil.Process(pid)
                name = proc.name()
            except:
                pass  # Fallback to "Unknown"
            return AppInfo(
                name=name,
                pid=pid,
                hwnd=hwnd,
                title=title,
                last_active=datetime.now()
            )
        except Exception:
            return None

# Global singleton session state - used across the application
session_state = SessionState()