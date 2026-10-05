import os
import json
import asyncio
import time
import urllib.parse
import subprocess
from typing import Dict, Any, Optional, Tuple
import win32gui
import win32process
import psutil
import win32con
import win32api
from dotenv import load_dotenv

try:
    from playwright.async_api import async_playwright, Browser, BrowserContext, Page
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

# User-provided Windows paths (FULL PATH TO PROFILE DIRECTORIES)
BRAVE_PROFILE_PATH = r"C:/Users/Vivek Sai/AppData/Local/BraveSoftware/Brave-Browser/User Data/Default"
# CHROME_PROFILE_PATH = r"C:/Users/Vivek Sai/AppData/Local/Google/Chrome/User Data/Profile 9"

# Derive base user data dir and profile directory for proper Chrome/Brave flags
import os.path
BRAVE_USER_DATA_DIR = os.path.dirname(BRAVE_PROFILE_PATH)  # ...\User Data
BRAVE_PROFILE_DIRECTORY = os.path.basename(BRAVE_PROFILE_PATH)  # "Default"

# CHROME_USER_DATA_DIR = os.path.dirname(CHROME_PROFILE_PATH)  # ...\User Data
# CHROME_PROFILE_DIRECTORY = os.path.basename(CHROME_PROFILE_PATH)  # "Profile 9"

# User-provided Windows paths
BRAVE_EXE_PATH = "C:/Program Files/BraveSoftware/Brave-Browser/Application/brave.exe"
# CHROME_EXE_PATH = "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"

#port numbers 
BRAVE_CDP_PORT = 9222
# CHROME_CDP_PORT = 9223
# Global variable to store the Playwright browser connection
_playwright_browser: Optional[Browser] = None
_playwright_context: Optional[BrowserContext] = None
_playwright_page: Optional[Page] = None
_current_command_page: Optional[Page] = None
_playwright_instance = None

def _get_browser_launch_info(browser_name: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Returns (exe_path, user_data_dir, profile_directory) for browser_name, or (None, None, None) if unsupported."""
    browser_name = browser_name.lower().strip()
    if browser_name == "brave":
        return BRAVE_EXE_PATH, BRAVE_USER_DATA_DIR, BRAVE_PROFILE_DIRECTORY
    # elif browser_name == "chrome":
    #     return CHROME_EXE_PATH, CHROME_USER_DATA_DIR, CHROME_PROFILE_DIRECTORY
    else:
        return None, None, None

async def _ensure_browser_ready_for_automation(browser_name: Optional[str] = None) -> Tuple[Optional[Browser], Optional[BrowserContext], Optional[Page]]:
    """
    Ensures a browser is running with remote debugging on port 9222.

    Logic:
    1. Check if we already have a valid Playwright connection
    2. Check for existing browser on port 9222 (with timeout)
    3. If none found, launch specified browser with debugging flags
    4. Wait for launched browser to accept CDP connections
    5. Return (browser, context, page) ready for automation

    Args:
        browser_name: If specified and no browser is ready, launch this browser.
                      If None, default to Brave.

    Returns:
        Tuple of (browser, context, page) ready for automation, or (None, None, None) on failure.
    """
    global _playwright_instance, _playwright_browser, _playwright_context, _playwright_page
    # Step 1: No existing browser found - launch specified browser (or default to Brave)
    target_browser ="brave"
    cdp_port = BRAVE_CDP_PORT
    
    # Step 1: Check if we already have a valid connection
    if _playwright_browser and _playwright_context and _playwright_page:
        try:
            if _playwright_browser.is_connected():
                return _playwright_browser, _playwright_context, _playwright_page
        except:
            pass  # Connection died, fall through to reconnect

    # Step 2: Check for existing browser on port 9222 (with timeout)
    print(f"Info: Checking for existing browser on port {cdp_port}...")
    start_check_time = time.time()
    check_timeout = 10  # Check for existing browser for up to 10 seconds

    while time.time() - start_check_time < check_timeout:
        try:
            playwright = await async_playwright().start()
            test_browser = await playwright.chromium.connect_over_cdp(f"http://localhost:{cdp_port}", timeout=10000)
            _playwright_instance = playwright

            contexts = test_browser.contexts
            if contexts and len(contexts) > 0:
                _playwright_browser = test_browser
                _playwright_context = contexts[0]
                pages = _playwright_context.pages
                _playwright_page = pages[0] if pages else await _playwright_context.new_page()
                print(f"Info: Found and connected to existing browser on port {cdp_port}")
                return _playwright_browser, _playwright_context, _playwright_page
        except Exception as e:
            # Browser not ready yet, continue checking
            print(f"CDP connection error: {e}")

        # Wait before next check
        await asyncio.sleep(2)  # Check every 2 seconds as requested

    print(f"Info: No existing browser found on port {cdp_port} after {check_timeout} seconds")

    
    exe_path, user_data_dir, profile_directory = _get_browser_launch_info(target_browser)

    if not exe_path or not user_data_dir or not profile_directory:
        # print(f"Error: Unsupported browser for automation: {target_browser}")
        return None, None, None

    # Check if executable exists
    if not os.path.isfile(exe_path):
        print(f"Error: Browser executable not found: {exe_path}")
        # print(f"Error: Please verify the path is correct: {exe_path}")
        return None, None, None

    # Launch browser with remote debugging, user data dir, and profile directory
    try:
        launch_args = [
            exe_path,
            f"--remote-debugging-port={cdp_port}",
            f"--user-data-dir={user_data_dir}",
            f"--profile-directory={profile_directory}"
        ]

        # print(f"Info: Launching {target_browser} with args: {launch_args}")
        process = subprocess.Popen(
            launch_args,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        # print(f"Info: {target_browser} process launched with PID: {process.pid}")

        # Step 4: Wait for launched browser to start listening on port 9222
        # print(f"Info: Waiting for {target_browser} to start listening on port {cdp_port}...")
        launch_start_time = time.time()
        launch_timeout = 20  # Wait up to 20 seconds for launched browser to be ready

        while time.time() - launch_start_time < launch_timeout:
            try:
                playwright = await async_playwright().start()
                browser = await playwright.chromium.connect_over_cdp(f"http://localhost:{cdp_port}", timeout=10000)
                _playwright_instance = playwright

                # Success! Set up our connection
                _playwright_browser = browser
                contexts = browser.contexts
                if contexts and len(contexts) > 0:
                    _playwright_context = contexts[0]
                    pages = _playwright_context.pages
                    _playwright_page = pages[0] if pages else await _playwright_context.new_page()
                    print(f"Info: Successfully connected to launched {target_browser} via CDP")
                    return _playwright_browser, _playwright_context, _playwright_page
                else:
                    await playwright.stop()
                    # Connected but no contexts - unlikely but handle gracefully
                    pass
            except Exception as e:
                # Browser not ready yet, continue checking
                print(f"CDP connection error: {e}")

            # Wait before next check
            await asyncio.sleep(2)  # Check every 2 seconds as requested

        # Timeout - clean up process
        print(f"Error: Timeout waiting for {target_browser} to start on port {cdp_port} after {launch_timeout} seconds")
        try:
            process.terminate()
            process.wait(timeout=5)
        except:
            try:
                process.kill()
            except:
                pass
        print(f"Info: Cleaned up {target_browser} process after timeout")
        return None, None, None

    except Exception as e:
        print(f"Error: Failed to launch {target_browser}: {e}")
        import traceback
        traceback.print_exc()
        return None, None, None
    
async def _get_page_for_command() -> Optional[Page]:
    global _current_command_page

    if _current_command_page and not _current_command_page.is_closed():
        return _current_command_page

    browser, context, _ = await _ensure_browser_ready_for_automation()

    if not browser or not context:
        return None

    _current_command_page = await context.new_page()
    return _current_command_page

async def get_current_page() -> Optional[Page]:
    """Return the current command page without creating a new tab."""
    if _current_command_page and not _current_command_page.is_closed():
        return _current_command_page
    return None

async def _bring_browser_to_foreground():
    """Brings the browser window to the foreground and sets focus."""
    try:
        # Get the browser window handle from the page's target info
        # This is approximate - we get the window via process ID
        if _playwright_browser and _playwright_context:
            # Get all contexts to find the one we're using
            for context in _playwright_browser.contexts:
                if context == _playwright_context:
                    # Get pages in this context
                    for page in context.pages:
                        if page == _current_command_page: 
                            # We have the page - get its target info to find the browser process
                            # Note: Playwright doesn't directly give us the HWND, so we'll use psutil
                            # to find the browser process and then its main window
                            try:
                                # Get browser process ID from Playwright (this is tricky)
                                # Fallback: find browser window by process name
                                browser_name = "brave" if _playwright_browser else "chrome"
                                exe_path, _, _ = _get_browser_launch_info(browser_name)
                                if exe_path:
                                    exe_name = os.path.basename(exe_path)
                                    all_hwnds = []
                                    def callback(hwnd, extra):
                                        if win32gui.IsWindowVisible(hwnd) and win32gui.IsWindowEnabled(hwnd):
                                            all_hwnds.append(hwnd)
                                        return True

                                    win32gui.EnumWindows(callback, None)
                                    windows = []
                                    for hwnd in all_hwnds:
                                        try:
                                            _, pid = win32process.GetWindowThreadProcessId(hwnd)
                                            proc = psutil.Process(pid)
                                            if proc.name().lower() == exe_name.lower():
                                                windows.append(hwnd)
                                                break
                                        except Exception:
                                            pass
                                    if windows:
                                        hwnd = windows[0]  # Take first matching window
                                        win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
                                        win32gui.BringWindowToTop(hwnd)

                                        foreground_hwnd = win32gui.GetForegroundWindow()
                                        current_thread = win32api.GetCurrentThreadId()
                                        foreground_thread = win32process.GetWindowThreadProcessId(foreground_hwnd)[0]
                                        target_thread = win32process.GetWindowThreadProcessId(hwnd)[0]

                                        win32process.AttachThreadInput(current_thread, foreground_thread, True)
                                        win32process.AttachThreadInput(current_thread, target_thread, True)

                                        try:
                                            win32gui.SetForegroundWindow(hwnd)
                                            win32gui.SetFocus(hwnd)
                                        finally:
                                            win32process.AttachThreadInput(current_thread, target_thread, False)
                                            win32process.AttachThreadInput(current_thread, foreground_thread, False)

                                        return
                                        
                            except Exception as e:
                                print(f"Error bringing browser to foreground: {e}")
                                pass
                            return
    except Exception as e:
        print(f"Error in _bring_browser_to_foreground: {e}")
        pass

def _normalize_url(target: str) -> str:
    """Normalize target to a full URL.

    Handles:
    - Full URLs: return as-is
    - Domains (contains dot, no spaces): prepend https://
    - Search terms: treat as Google search
    - Special Gmail handling: if target contains 'gmail' or 'vitapstudent',
      we might want to specify the account, but we'll keep it general for now
      and rely on browser's loaded account or let user specify full URL with u/0/u/1
    """
    target = target.strip()
    if not target:
        return ""

    # If it's already a full URL, return as-is
    if target.startswith(("http://", "https://")):
        return target

    # If it looks like a domain (contains dot and no spaces), prepend https://
    if "." in target and " " not in target:
        # Special handling for Gmail - if they want a specific account, they should
        # specify the full URL with u/0/u/1 in the target
        return f"https://{target}"

    # Otherwise, treat as a search term for Google
    return f"https://www.google.com/search?q={urllib.parse.quote_plus(target)}"

async def _update_session_state_from_page(page: Page):
    """Update session state with current page URL."""
    try:
        if page and not page.is_closed():
            url = page.url
            if url:
                # Import here to avoid circular imports
                from ..session.tracker import session_state
                session_state.last_browser_url = url
    except Exception as e:
        print(f"Failed to update session state: {e}")

async def open(target: str) -> Dict[str, Any]:
    """
    Opens a website in the browser ready for automation.
    Ensures browser is running with debugging, brings to foreground, then navigates.
    """
    if not PLAYWRIGHT_AVAILABLE:
        return {
            "status": "error",
            "message": "Playwright not installed. Install with: pip install playwright",
            "failed_command": {"action": "open_website", "target": target}
        }

    try:
        target_normalized = target.strip()

        if not target_normalized:
            return {
                "status": "error",
                "message": "Empty website target",
                "failed_command": {
                    "action": "open_website",
                    "target": target
                }
            }

        # Normalize to URL
        url = _normalize_url(target_normalized)

        # Ensure browser is ready for automation
        page = await _get_page_for_command()
        if not page:
            return {
                "status": "error",
                "message": "Failed to ensure browser is ready for automation. "
                           "Please check that Brave or Chrome can be launched, "
                           "or manually start a browser with --remote-debugging-port=9222.",
                "failed_command": {
                    "action": "open_website",
                    "target": target
                }
            }

        # Bring browser window to foreground
        await _bring_browser_to_foreground()

        # Ensure we're on a valid page
        # if page.is_closed():
        #     # Get a new page
        #     pages = context.pages
        #     if pages:
        #         page = pages[0]
        #     else:
        #         page = await context.new_page()

        # Navigate to the URL
        await page.goto(url, wait_until="domcontentloaded", timeout=10000)

        # Update session state
        await _update_session_state_from_page(page)

        return {
            "status": "success",
            "message": f"Navigated to {url}",
            "data": {
                "url": url
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
    Performs a search in the browser ready for automation.
    Context-aware: uses site-specific search when possible (e.g., YouTube search on youtube.com),
    falls back to Google search otherwise.
    """
    if not PLAYWRIGHT_AVAILABLE:
        return {
            "status": "error",
            "message": "Playwright not installed. Install with: pip install playwright",
            "failed_command": {
                "action": "search",
                "target": target
            }
        }

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

        # Ensure browser is ready for automation
        page = await _get_page_for_command()
        if not page:
            return {
                "status": "error",
                "message": "Failed to ensure browser is ready for automation. "
                           "Please check that Brave or Chrome can be launched, "
                           "or manually start a browser with --remote-debugging-port=9222.",
                "failed_command": {
                    "action": "search",
                    "target": target
                }
            }

        # Bring browser window to foreground
        await _bring_browser_to_foreground()

        # Ensure we're on a valid page
        # if page.is_closed():
        #     # Get a new page
        #     pages = context.pages
        #     if pages:
        #         page = pages[0]
        #     else:
        #         page = await context.new_page()

        # Get current URL to determine search context
        current_url = page.url if not page.is_closed() else ""
        # Also check session state as fallback
        if not current_url:
            try:
                from ..session.tracker import session_state
                current_url = session_state.last_browser_url
            except:
                current_url = ""

        # Determine search URL based on current context
        search_url = ""
        if "youtube.com" in current_url.lower():
            # YouTube search
            search_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(target_normalized)}"
        elif "mail.google.com" in current_url.lower() or "gmail.com" in current_url.lower():
            # Gmail search
            search_url = f"https://mail.google.com/mail/u/0/#search/{urllib.parse.quote_plus(target_normalized)}"
        elif "." in current_url.lower() and current_url.lower().startswith("http"):
            # Generic site search - try to append search query
            # This is a simplified approach; for better results we'd need site-specific handlers
            if "?" in current_url:
                search_url = f"{current_url}&q={urllib.parse.quote_plus(target_normalized)}"
            else:
                search_url = f"{current_url}?q={urllib.parse.quote_plus(target_normalized)}"
        else:
            # Fall back to Google search
            search_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(target_normalized)}"

        # Perform the search by navigating to search URL
        await page.goto(search_url, wait_until="domcontentloaded", timeout=10000)

        # Update session state
        await _update_session_state_from_page(page)

        return {
            "status": "success",
            "message": f"Searched for '{target_normalized}'",
            "data": {
                "url": search_url
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

async def browser_click(target: str) -> Dict[str, Any]:
    """
    Click an element in the current page via CDP connection.
    target: CSS selector or XPath (if starts with '//')
    """
    if not PLAYWRIGHT_AVAILABLE:
        return {
            "status": "error",
            "message": "Playwright not installed. Install with: pip install playwright",
            "failed_command": {"action": "browser_click", "target": target}
        }

    try:
        # Ensure browser is ready for automation
        page = await _get_page_for_command()
        if not page:
            return {
                "status": "error",
                "message": "Failed to ensure browser is ready for automation. "
                           "Please check that Brave or Chrome can be launched, "
                           "or manually start a browser with --remote-debugging-port=9222.",
                "failed_command": {"action": "browser_click", "target": target}
            }

        # Bring browser window to foreground
        await _bring_browser_to_foreground()

        # Ensure we're on a valid page
        # if page.is_closed():
        #     # Get a new page
        #     pages = context.pages
        #     if pages:
        #         page = pages[0]
        #     else:
        #         page = await context.new_page()

        # Click the element
        if target.startswith("//"):
            # XPath selector
            await page.wait_for_selector(target, state="attached", timeout=5000)
            await page.click(target)
        else:
            # CSS selector
            await page.wait_for_selector(target, state="attached", timeout=5000)
            await page.click(target)

        # Wait briefly for any navigation/actions to start
        await page.wait_for_timeout(1000)

        # Update session state
        await _update_session_state_from_page(page)

        return {
            "status": "success",
            "message": f"Clicked element: {target}",
            "data": {
                "selector": target,
                "url": page.url
            }
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to click element: {str(e)}",
            "failed_command": {"action": "browser_click", "target": target}
        }

async def browser_type(target: str) -> Dict[str, Any]:
    """
    Type text into an element in the current page via CDP connection.
    target: format "selector|text" where selector is CSS or XPath (if starts with '//')
    """
    if not PLAYWRIGHT_AVAILABLE:
        return {
            "status": "error",
            "message": "Playwright not installed. Install with: pip install playwright",
            "failed_command": {"action": "browser_type", "target": target}
        }

    try:
        # Parse target as "selector|text"
        if "|" not in target:
            return {
                "status": "error",
                "message": "Invalid target format for browser_type. Use 'selector|text'",
                "failed_command": {"action": "browser_type", "target": target}
            }

        selector, text = target.split("|", 1)
        selector = selector.strip()
        text = text.strip()

        # Ensure browser is ready for automation
        page = await _get_page_for_command()
        if not page:
            return {
                "status": "error",
                "message": "Failed to ensure browser is ready for automation. "
                           "Please check that Brave or Chrome can be launched, "
                           "or manually start a browser with --remote-debugging-port=9222.",
                "failed_command": {"action": "browser_type", "target": target}
            }

        # Bring browser window to foreground
        await _bring_browser_to_foreground()

        # Ensure we're on a valid page
        # if page.is_closed():
        #     # Get a new page
        #     pages = context.pages
        #     if pages:
        #         page = pages[0]
        #     else:
        #         page = await context.new_page()

        # Type into the element
        if selector.startswith("//"):
            # XPath selector
            await page.wait_for_selector(selector, state="attached", timeout=5000)
            await page.fill(selector, text)
        else:
            # CSS selector
            await page.wait_for_selector(selector, state="attached", timeout=5000)
            await page.fill(selector, text)

        # Update session state
        await _update_session_state_from_page(page)

        return {
            "status": "success",
            "message": f"Typed '{text}' into {selector}",
            "data": {
                "selector": selector,
                "text": text,
                "url": page.url
            }
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to type text: {str(e)}",
            "failed_command": {"action": "browser_type", "target": target}
        }

async def browser_press(target: str) -> Dict[str, Any]:
    """
    Press a key/combo in the current page via CDP connection.
    target: key name (e.g., "Enter", "Tab", "Escape") or combo (e.g., "Control+C")
    """
    if not PLAYWRIGHT_AVAILABLE:
        return {
            "status": "error",
            "message": "Playwright not installed. Install with: pip install playwright",
            "failed_command": {"action": "browser_press", "target": target}
        }

    try:
        # Ensure browser is ready for automation
        page = await _get_page_for_command()
        if not page:
            return {
                "status": "error",
                "message": "Failed to ensure browser is ready for automation. "
                           "Please check that Brave or Chrome can be launched, "
                           "or manually start a browser with --remote-debugging-port=9222.",
                "failed_command": {"action": "browser_press", "target": target}
            }

        # Bring browser window to foreground
        await _bring_browser_to_foreground()

        # Ensure we're on a valid page
        # if page.is_closed():
        #     # Get a new page
        #     pages = context.pages
        #     if pages:
        #         page = pages[0]
        #     else:
        #         page = await context.new_page()

        # Parse the key combination
        key_mapping = {
            "enter": "Enter",
            "return": "Enter",
            "tab": "Tab",
            "escape": "Escape",
            "esc": "Escape",
            "space": " ",
            "up": "ArrowUp",
            "down": "ArrowDown",
            "left": "ArrowLeft",
            "right": "ArrowRight",
            "backspace": "Backspace",
            "delete": "Delete",
            "home": "Home",
            "end": "End",
            "pageup": "PageUp",
            "pagedown": "PageDown",
            "f1": "F1", "f2": "F2", "f3": "F3", "f4": "F4", "f5": "F5",
            "f6": "F6", "f7": "F7", "f8": "F8", "f9": "F9", "f10": "F10",
            "f11": "F11", "f12": "F12"
        }

        # Handle key combinations (e.g., "Control+C" or "Ctrl+C")
        target_lower = target.lower().strip()
        if "+" in target_lower:
            # Split by + and map each part
            parts = [part.strip() for part in target_lower.split("+")]
            key_parts = []
            for part in parts:
                if part in ["ctrl", "control"]:
                    key_parts.append("Control")
                elif part in ["alt"]:
                    key_parts.append("Alt")
                elif part in ["shift"]:
                    key_parts.append("Shift")
                elif part in key_mapping:
                    key_parts.append(key_mapping[part])
                else:
                    # Single character
                    key_parts.append(part)

            # Press the combination
            await page.keyboard.down("Control") if "control" in parts or "ctrl" in parts else None
            await page.keyboard.down("Alt") if "alt" in parts else None
            await page.keyboard.down("Shift") if "shift" in parts else None

            # Press the main key (last non-modifier key)
            main_key = None
            for part in reversed(parts):
                if part not in ["ctrl", "control", "alt", "shift"]:
                    main_key = key_mapping.get(part, part)
                    break

            if main_key:
                await page.keyboard.press(main_key)

            # Release modifiers in reverse order
            await page.keyboard.up("Shift") if "shift" in parts else None
            await page.keyboard.up("Alt") if "alt" in parts else None
        else:
            # Single key
            if target_lower in key_mapping:
                key = key_mapping[target_lower]
            else:
                # Assume it's a single character
                key = target_lower

            await page.keyboard.press(key)

        # Wait briefly for any actions to start
        await page.wait_for_timeout(500)

        # Update session state
        await _update_session_state_from_page(page)

        return {
            "status": "success",
            "message": f"Pressed key(s): {target}",
            "data": {
                "keys": target,
                "url": page.url
            }
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to press key(s): {str(e)}",
            "failed_command": {"action": "browser_press", "target": target}
        }