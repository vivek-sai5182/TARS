import os
import json
import subprocess
import time
import urllib.parse
from typing import Dict, Any, Optional, Tuple
import win32gui
import win32process
import win32api
import win32con
import psutil

try:
    from pywinauto import Application
    from pywinauto.findwindows import ElementNotFoundError
    PYWINAUTO_AVAILABLE = True
except ImportError:
    PYWINAUTO_AVAILABLE = False

# Browser configuration: maps browser names to their executable names and process names
BROWSER_CONFIG = {
    "brave": {
        "exe": "C:/Program Files/BraveSoftware/Brave-Browser/Application/brave.exe",
        "process": "brave.exe",
        "name": "Brave"
    },
    "chrome": {
        "exe": "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
        "process": "chrome.exe",
        "name": "Chrome"
    }
}

def _get_browser_executable(browser_name: str) -> Optional[str]:
    """Get the executable path for a browser from PATH or common locations."""
    browser_name = browser_name.lower()
    if browser_name not in BROWSER_CONFIG:
        return None

    config = BROWSER_CONFIG[browser_name]
    if not config:
        return None

    exe_path = config["exe"]
    return exe_path if os.path.isfile(exe_path) else None

def _is_browser_window(hwnd: int, browser_name: str) -> bool:
    """Check if a window belongs to the specified browser."""
    if not win32gui.IsWindow(hwnd):
        return False

    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        proc = psutil.Process(pid)
        return proc.name().lower() == BROWSER_CONFIG[browser_name.lower()]["process"].lower()
    except (psutil.NoSuchProcess, psutil.AccessDenied, KeyError):
        return False

def _find_browser_window(browser_name: str = "brave") -> int:
    """Find a window belonging to the specified browser."""
    browser_name = browser_name.lower()

    if browser_name not in BROWSER_CONFIG:
        return 0

    def callback(hwnd, windows):
        if win32gui.IsWindowVisible(hwnd) and win32gui.IsWindowEnabled(hwnd):
            if _is_browser_window(hwnd, browser_name):
                windows.append(hwnd)
        return True

    windows = []
    win32gui.EnumWindows(callback, windows)

    return windows[0] if windows else 0

def _get_last_browser_window() -> Tuple[Optional[int], Optional[str]]:
    """Get the last browser window from session state."""
    try:
        from ..session.tracker import session_state
        hwnd = session_state.focused_window
        if hwnd:  # Default to brave check
            # Check if it's actually a browser window (any browser)
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            try:
                proc = psutil.Process(pid)
                proc_name = proc.name().lower()
                for browser in BROWSER_CONFIG.values():
                    if proc_name == browser["process"].lower():
                        return hwnd, browser["name"]
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except (ImportError, AttributeError):
        pass
    return None, None

def _focus_window(hwnd: int):
    """Bring a window to the foreground and set focus."""
    if win32gui.IsWindow(hwnd):
        win32gui.ShowWindow(hwnd, 5)  # SW_SHOW
        win32gui.BringWindowToTop(hwnd)
        win32gui.SetForegroundWindow(hwnd)

def _launch_browser(browser_name: str, url: str) -> Tuple[bool, str, Optional[int]]:
    """Launch a browser with a URL and return (success, message, pid)."""
    browser_name = browser_name.lower()
    if browser_name not in BROWSER_CONFIG:
        return False, f"Unsupported browser: {browser_name}", None

    exe_path = _get_browser_executable(browser_name)
    if not exe_path:
        return False, f"Could not find executable for {browser_name}", None

    try:
        # Launch the browser with the URL
        process = subprocess.Popen(
            [exe_path, url],
            creationflags=subprocess.CREATE_NO_WINDOW
        )

        return True, "", process.pid
    except Exception as e:
        return False, str(e), None

def _navigate_to_url(hwnd: int, url: str) -> bool:
    """Navigate to a URL in an existing browser window using keyboard shortcuts."""
    if not PYWINAUTO_AVAILABLE:
        return False

    try:
        # Connect to the browser window
        app = Application().connect(handle=hwnd, timeout=5)
        window = app.window(handle=hwnd)

        # Focus the address bar (Ctrl+L)
        window.type_keys('^l')
        time.sleep(0.5)

        # Clear existing text
        window.type_keys('^a{BACKSPACE}')
        time.sleep(0.2)

        # Type URL and press Enter
        window.type_keys(url, with_spaces=True)
        time.sleep(0.5)
        window.type_keys('{ENTER}')
        time.sleep(2)  # Wait for navigation to start

        return True
    except Exception:
        return False

def _get_website_url(target: str) -> str:
    """Convert a website name to its URL."""
    target_lower = target.lower().strip()

    # If it's already a URL, return as-is
    if target_lower.startswith(("http://", "https://")):
        return target

    # Common website mappings
    website_map = {
        "youtube": "https://www.youtube.com",
        "gmail": "https://mail.google.com",
        "chatgpt": "https://chat.openai.com",
        "google": "https://www.google.com",
        "github": "https://github.com",
        "stackoverflow": "https://stackoverflow.com",
        "reddit": "https://www.reddit.com",
        "netflix": "https://www.netflix.com",
        "spotify": "https://open.spotify.com",
        "twitch": "https://www.twitch.tv",
        "facebook": "https://www.facebook.com",
        "twitter": "https://twitter.com",
        "instagram": "https://www.instagram.com",
        "linkedin": "https://www.linkedin.com",
        "whatsapp": "https://web.whatsapp.com",
        "amazon": "https://www.amazon.com",
    }

    return website_map.get(target_lower, f"https://www.google.com/search?q={urllib.parse.quote_plus(target)}")

def _get_search_url(browser_url: str, search_term: str) -> str:
    """Generate a search URL for the current website."""
    parsed = urllib.parse.urlparse(browser_url)
    domain = parsed.netloc.lower()

    # Site-specific search URLs
    search_engines = {
        "youtube.com": "https://www.youtube.com/results?search_query={}",
        "gmail.com": "https://mail.google.com/mail/u/0/#search/{}",
        "google.com": "https://www.google.com/search?q={}",
        "github.com": "https://github.com/search?q={}",
        "stackoverflow.com": "https://stackoverflow.com/search?q={}",
        "reddit.com": "https://www.reddit.com/search/?q={}",
        "netflix.com": "https://www.netflix.com/search?q={}",
        "spotify.com": "https://open.spotify.com/search/{}",
        "twitch.tv": "https://www.twitch.tv/search?term={}",
        "facebook.com": "https://www.facebook.com/search/top/?q={}",
        "twitter.com": "https://twitter.com/search?q={}",
        "instagram.com": "https://www.instagram.com/explore/tags/{}/",
        "linkedin.com": "https://www.linkedin.com/search/results/all/?keywords={}&origin=SWITCH_SEARCH_VERTICAL",
        "whatsapp.com": "https://web.whatsapp.com/#search/{}",
        "amazon.com": "https://www.amazon.com/s?k={}",
    }

    # Check for exact domain match
    if domain in search_engines:
        return search_engines[domain].format(urllib.parse.quote_plus(search_term))

    # Check for domain containing known sites
    for site, url_pattern in search_engines.items():
        if site in domain:
            return url_pattern.format(urllib.parse.quote_plus(search_term))

    # Default to Google search
    return f"https://www.google.com/search?q={urllib.parse.quote_plus(search_term)}"

async def open(target: str) -> Dict[str, Any]:
    """
    Opens a website in the appropriate browser.
    If no browser is specified in context, uses Brave as default.
    """
    try:
        target_normalized = target.lower().strip()

        if not target_normalized:
            return {
                "status": "error",
                "message": "Empty website target",
                "failed_command": {
                    "action": "open_website",
                    "target": target
                }
            }

        # Get the website URL
        url = _get_website_url(target_normalized)

        # Get the last browser window from session state
        last_hwnd, last_browser = _get_last_browser_window()

        # First, try to use the last browser window
        if last_hwnd is not None and last_browser is not None:
            try:
                _focus_window(last_hwnd)

                if _navigate_to_url(last_hwnd, url):
                    return {
                        "status": "success",
                        "message": f"Navigated {last_browser} to {url}",
                        "data": {
                            "url": url,
                            "hwnd": last_hwnd
                        }
                    }

            except Exception:
                pass

        # If the session window failed, find another window
        # belonging to the same browser
        if last_browser is not None:
            hwnd = _find_browser_window(last_browser)

            if hwnd != 0:
                try:
                    _focus_window(hwnd)

                    if _navigate_to_url(hwnd, url):
                        return {
                            "status": "success",
                            "message": f"Navigated {last_browser} to {url}",
                            "data": {
                                "url": url,
                                "hwnd": hwnd
                            }
                        }

                except Exception:
                    pass

        # No usable existing browser - launch a new one
        browser_name = last_browser.lower() if last_browser else "brave"

        success, message, pid = _launch_browser(browser_name, url)

        if not success:
            return {
                "status": "error",
                "message": f"Failed to launch {browser_name}: {message}",
                "failed_command": {
                    "action": "open_website",
                    "target": target
                }
            }

        # Wait for the browser window to appear
        hwnd = 0
        start_time = time.time()

        while time.time() - start_time < 10:
            hwnd = _find_browser_window(browser_name)

            if hwnd != 0:
                try:
                    _, found_pid = win32process.GetWindowThreadProcessId(hwnd)

                    if found_pid == pid:
                        break

                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            time.sleep(0.5)

        # Fallback to any window of that browser
        if hwnd == 0:
            hwnd = _find_browser_window(browser_name)

        return {
            "status": "success",
            "message": f"Launched {browser_name} and navigated to {url}",
            "data": {
                "url": url,
                "hwnd": hwnd,
                "pid": pid
            }
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to open website: {str(e)}",
            "failed_command": {
                "action": "open_website",
                "target": target
            }
        }
        
async def search(target: str) -> Dict[str, Any]:
    """
    Performs a search in the current browser context.
    Uses the current window's website to determine the search engine.
    """
    try:
        target_normalized = target.strip()

        if not target_normalized:
            return {
                "status": "error",
                "message": "Empty search term",
                "failed_command": {
                    "action": "search",
                    "target": target
                }
            }

        # Get the last browser window from session state
        last_hwnd, last_browser = _get_last_browser_window()

        # If there is no browser window, launch Brave with Google search
        if not last_hwnd:
            url = (
                "https://www.google.com/search?q="
                + urllib.parse.quote_plus(target_normalized)
            )

            success, message, pid = _launch_browser("brave", url)

            if not success:
                return {
                    "status": "error",
                    "message": f"Failed to launch Brave: {message}",
                    "failed_command": {
                        "action": "search",
                        "target": target
                    }
                }

            hwnd = 0
            start_time = time.time()

            while time.time() - start_time < 10:
                hwnd = _find_browser_window("brave")

                if hwnd != 0:
                    try:
                        _, found_pid = win32process.GetWindowThreadProcessId(hwnd)

                        if found_pid == pid:
                            break

                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass

                time.sleep(0.5)

            if hwnd == 0:
                hwnd = _find_browser_window("brave")

            return {
                "status": "success",
                "message": f"Launched Brave and searched for '{target_normalized}'",
                "data": {
                    "url": url,
                    "hwnd": hwnd,
                    "pid": pid
                }
            }

        # Get current URL from session state
        current_url = ""

        try:
            from ..session.tracker import session_state
            current_url = session_state.last_browser_url
        except (ImportError, AttributeError):
            pass

        # If we don't have a current URL, use the window title
        if not current_url:
            try:
                window_title = win32gui.GetWindowText(last_hwnd)

                if "youtube" in window_title.lower():
                    current_url = "https://www.youtube.com"
                elif "gmail" in window_title.lower():
                    current_url = "https://mail.google.com"
                elif "google" in window_title.lower():
                    current_url = "https://www.google.com"
                else:
                    current_url = "https://www.google.com"

            except Exception:
                current_url = "https://www.google.com"

        # Generate the search URL
        search_url = _get_search_url(
            current_url,
            target_normalized
        )

        # First, try the browser window from session state
        if last_browser is not None:
            try:
                _focus_window(last_hwnd)

                if _navigate_to_url(last_hwnd, search_url):
                    return {
                        "status": "success",
                        "message": f"Searched for '{target_normalized}' in {last_browser}",
                        "data": {
                            "url": search_url,
                            "hwnd": last_hwnd
                        }
                    }

            except Exception:
                pass

        # If that failed, find another window of the same browser
        if last_browser is not None:
            hwnd = _find_browser_window(last_browser)

            if hwnd != 0:
                try:
                    _focus_window(hwnd)

                    if _navigate_to_url(hwnd, search_url):
                        return {
                            "status": "success",
                            "message": f"Searched for '{target_normalized}' in {last_browser}",
                            "data": {
                                "url": search_url,
                                "hwnd": hwnd
                            }
                        }

                except Exception:
                    pass

        # If navigation failed, launch a new browser instance
        browser_name = last_browser.lower() if last_browser else "brave"

        success, message, pid = _launch_browser(
            browser_name,
            search_url
        )

        if not success:
            return {
                "status": "error",
                "message": f"Failed to launch {browser_name}: {message}",
                "failed_command": {
                    "action": "search",
                    "target": target
                }
            }

        # Wait for the browser window to appear
        hwnd = 0
        start_time = time.time()

        while time.time() - start_time < 10:
            hwnd = _find_browser_window(browser_name)

            if hwnd != 0:
                try:
                    _, found_pid = win32process.GetWindowThreadProcessId(hwnd)

                    if found_pid == pid:
                        break

                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            time.sleep(0.5)

        if hwnd == 0:
            hwnd = _find_browser_window(browser_name)

        return {
            "status": "success",
            "message": f"Launched {browser_name} and searched for '{target_normalized}'",
            "data": {
                "url": search_url,
                "hwnd": hwnd,
                "pid": pid
            }
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to perform search: {str(e)}",
            "failed_command": {
                "action": "search",
                "target": target
            }
        }
async def wait(seconds: str) -> Dict[str, Any]:
    """
    Pauses execution for specified number of seconds.
    """
    try:
        sec = float(seconds)
        await asyncio.sleep(sec)
        return {
            "status": "success",
            "message": f"Waited {seconds} seconds",
            "data": {"seconds": sec}
        }
    except ValueError:
        return {
            "status": "error",
            "message": f"Invalid wait time: {seconds}. Must be a number.",
            "failed_command": {"action": "wait", "target": seconds}
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Wait failed: {str(e)}",
            "failed_command": {"action": "wait", "target": seconds}
        }