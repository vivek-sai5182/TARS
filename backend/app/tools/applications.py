import os
import json
import subprocess
import time
import urllib.parse
from typing import Dict, Any, Tuple, Optional
import win32gui
import win32process
import win32api
import win32con
import win32com.shell
import psutil
import shutil

try:
    from pywinauto import Application
    from pywinauto.findwindows import ElementNotFoundError
    PYWINAUTO_AVAILABLE = True
except ImportError:
    PYWINAUTO_AVAILABLE = False

def _resolve_uri_scheme(target: str) -> Optional[str]:
    """Map common application names to Windows URI schemes."""
    uri_map = {
        "settings": "ms-settings:",
        "privacy": "ms-settings:privacy",
        "system": "ms-settings:system",
        "display": "ms-settings:display",
        "sound": "ms-settings:sound",
        "notifications": "ms-settings:notifications",
        "focusassist": "ms-settings:focusassist",
        "storagesense": "ms-settings:storagesense",
        "appsfeatures": "ms-settings:appsfeatures",
        "defaultapps": "ms-settings:defaultapps",
        "offlinemaps": "ms-settings:offlinemaps",
        "facebook": "facebook:",
        "twitter": "twitter:",
    }
    return uri_map.get(target)

def _resolve_via_start_menu(target: str) -> Optional[str]:
    """Search Start Menu shortcuts (.lnk files) for the target."""
    # Common Start Menu locations
    start_menu_paths = [
        os.path.join(os.getenv('APPDATA'), 'Microsoft', 'Windows', 'Start Menu', 'Programs'),
        os.path.join(os.getenv('PROGRAMDATA'), 'Microsoft', 'Windows', 'Start Menu', 'Programs'),
    ]

    target_lower = target.lower()
    for start_menu in start_menu_paths:
        if not os.path.exists(start_menu):
            continue

        # Walk through all shortcuts
        for root, dirs, files in os.walk(start_menu):
            for file in files:
                if file.lower().endswith('.lnk'):
                    # Get the shortcut name without extension
                    shortcut_name = os.path.splitext(file)[0].lower()
                    if target_lower in shortcut_name or shortcut_name in target_lower:
                        return os.path.join(root, file)
    return None

def _resolve_via_appx(target: str) -> Optional[Tuple[str, str]]:
    """
    Check for AppX (Microsoft Store) packages via Windows Registry.
    Returns (package_family_name, app_user_model_id) if found.
    """
    try:
        import winreg
        # Registry path for AppX packages
        reg_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Appx\AppxAllUserStore"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path) as key:
            i = 0
            while True:
                try:
                    subkey_name = winreg.EnumKey(key, i)
                    subkey_path = f"{reg_path}\\{subkey_name}"
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, subkey_path) as subkey:
                        try:
                            # Try to get the package display name
                            display_name, _ = winreg.QueryValueEx(subkey, "DisplayName")
                            if target.lower() in display_name.lower():
                                # Get Package Family Name and AppUserModelID
                                package_family, _ = winreg.QueryValueEx(subkey, "PackageFamilyName")
                                app_user_model_id, _ = winreg.QueryValueEx(subkey, "AppUserModelID")
                                return (package_family, app_user_model_id)
                        except FileNotFoundError:
                            pass
                    i += 1
                except OSError:
                    break
    except Exception:
        pass
    return None

def _resolve_via_executable_search(target: str) -> Optional[str]:
    """Search for executable in PATH and common installation directories."""
    # Check if target already looks like an executable
    if target.endswith('.exe') or target.endswith('.com') or target.endswith('.bat'):
        # Check if it exists in PATH or current directory
        if shutil.which(target):
            return shutil.which(target)
        if os.path.isfile(target):
            return os.path.abspath(target)
        return None

    # Try with .exe extension
    exe_target = f"{target}.exe"
    if shutil.which(exe_target):
        return shutil.which(exe_target)

    # Common installation directories
    common_paths = [
        os.getenv('PROGRAMFILES'),
        os.getenv('PROGRAMFILES(X86)'),
        os.getenv('LOCALAPPDATA'),
        os.getenv('APPDATA'),
        os.getenv('USERPROFILE'),
    ]

    for path in common_paths:
        if not path or not os.path.exists(path):
            continue

        # Search for exe files containing the target name
        for root, dirs, files in os.walk(path):
            for file in files:
                if file.lower().endswith('.exe'):
                    if target.lower() in file.lower():
                        return os.path.join(root, file)
    return None

def _launch_via_shell_execute(uri: str) -> Tuple[bool, str]:
    """Launch via ShellExecute for URI schemes."""
    try:
        result = win32api.ShellExecute(
            0,           # hwnd
            "open",      # operation
            uri,         # file (URI)
            None,        # parameters
            None,        # directory
            win32con.SW_SHOWNORMAL  # show command
        )
        # ShellExecute returns >32 on success
        return result > 32, ""
    except Exception as e:
        return False, str(e)

def _launch_via_start_menu(shortcut_path: str) -> Tuple[bool, str]:
    """Launch via Start Menu shortcut (.lnk file)."""
    try:
        result = win32api.ShellExecute(
            0,
            "open",
            shortcut_path,
            None,
            None,
            win32con.SW_SHOWNORMAL
        )
        return result > 32, ""
    except Exception as e:
        return False, str(e)

def _launch_via_appx(package_family: str, app_user_model_id: str) -> Tuple[bool, str]:
    """Launch AppX package using its AppUserModelID."""
    try:
        # Construct the shell command for launching AppX
        shell_cmd = f"explorer.exe shell:Apps\\{package_family}!{app_user_model_id}"
        result = win32api.ShellExecute(
            0,
            "open",
            shell_cmd,
            None,
            None,
            win32con.SW_SHOWNORMAL
        )
        return result > 32, ""
    except Exception as e:
        return False, str(e)

def _launch_via_executable(exe_path: str) -> Tuple[bool, str, Optional[int]]:
    """Launch executable and return PID if successful."""
    try:
        process = subprocess.Popen(
            [exe_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        return True, "", process.pid
    except Exception as e:
        return False, str(e), None

def _find_window_by_pid(pid: int, timeout: int = 5) -> int:
    """Find the main window handle for a given PID."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        def callback(hwnd, hwnds):
            if win32gui.IsWindowVisible(hwnd) and win32gui.IsWindowEnabled(hwnd):
                _, found_pid = win32process.GetWindowThreadProcessId(hwnd)
                if found_pid == pid:
                    hwnds.append(hwnd)
            return True

        windows = []
        win32gui.EnumWindows(callback, windows)
        if windows:
            # Return the first window found (usually the main window)
            return windows[0]
        time.sleep(0.1)
    return 0

def _find_window_by_title(title_substring: str, timeout: int = 5) -> int:
    """Find a window whose title contains the given substring."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        def callback(hwnd, windows):
            if win32gui.IsWindowVisible(hwnd) and win32gui.IsWindowEnabled(hwnd):
                window_text = win32gui.GetWindowText(hwnd)
                if title_substring.lower() in window_text.lower():
                    windows.append(hwnd)
            return True

        windows = []
        win32gui.EnumWindows(callback, windows)
        if windows:
            # Return the first matching window
            return windows[0]
        time.sleep(0.1)
    return 0

async def open(target: str) -> Dict[str, Any]:
    """
    Launches a Windows application using Windows-native resolution mechanisms.
    Resolution order:
    1. URI schemes (ms-settings: etc.)
    2. Start Menu shortcuts (.lnk files)
    3. AppX packages (Microsoft Store apps)
    4. Executable search (PATH and common directories)
    """
    try:
        target_normalized = target.lower().strip()
        if not target_normalized:
            return {
                "status": "error",
                "message": "Empty application target",
                "failed_command": {"action": "open_application", "target": target}
            }

        launch_method = None
        launch_info = None

        # Step 1: Check URI schemes
        uri = _resolve_uri_scheme(target_normalized)
        if uri:
            launch_method = "uri"
            launch_info = uri

        # Step 2: Check Start Menu shortcuts
        if not launch_method:
            shortcut_path = _resolve_via_start_menu(target_normalized)
            if shortcut_path:
                launch_method = "start_menu"
                launch_info = shortcut_path

        # Step 3: Check AppX packages
        if not launch_method:
            appx_info = _resolve_via_appx(target_normalized)
            if appx_info:
                launch_method = "appx"
                launch_info = appx_info

        # Step 4: Check executable search
        if not launch_method:
            exe_path = _resolve_via_executable_search(target_normalized)
            if exe_path:
                launch_method = "executable"
                launch_info = exe_path

        # If no resolution method found, return error
        if not launch_method:
            return {
                "status": "error",
                "message": f"Application not found: '{target}'. "
                        f"Try checking Start Menu, reinstalling, or using the exact name.",
                "failed_command": {"action": "open_application", "target": target}
            }

        # Launch based on the determined method
        success = False
        message = ""
        pid = None

        if launch_method == "uri":
            success, message = _launch_via_shell_execute(launch_info)
            if success:
                # For URI schemes, try to find window by title (capitalized target)
                title_hint = target_normalized.capitalize()
                hwnd = _find_window_by_title(title_hint, timeout=3)
                if not hwnd:
                    # Try with common title variations
                    hwnd = _find_window_by_title(target_normalized, timeout=2)
                if not hwnd:
                    hwnd = _find_window_by_title("Settings", timeout=2)  # Special case for settings
        elif launch_method == "start_menu":
            success, message = _launch_via_start_menu(launch_info)
            if success:
                # Extract app name from shortcut for window search
                shortcut_name = os.path.splitext(os.path.basename(launch_info))[0]
                hwnd = _find_window_by_title(shortcut_name, timeout=3)
                if not hwnd:
                    hwnd = _find_window_by_title(target_normalized, timeout=2)
        elif launch_method == "appx":
            package_family, app_user_model_id = launch_info
            success, message = _launch_via_appx(package_family, app_user_model_id)
            if success:
                # For AppX, try to find window by package family name or app name
                hwnd = _find_window_by_title(package_family, timeout=3)
                if not hwnd:
                    hwnd = _find_window_by_title(target_normalized, timeout=2)
        elif launch_method == "executable":
            success, message, pid = _launch_via_executable(launch_info)
            if success and pid:
                # Wait briefly for window to appear
                time.sleep(1)
                hwnd = _find_window_by_pid(pid, timeout=3)
            else:
                hwnd = 0

        if not success:
            return {
                "status": "error",
                "message": f"Failed to launch {target}: {message}",
                "failed_command": {"action": "open_application", "target": target}
            }

        # Ensure we have an hwnd for session tracking
        if not hwnd:
            hwnd = _find_window_by_title(target_normalized, timeout=2)

        return {
            "status": "success",
            "message": f"Opened {target}",
            "data": {
                "pid": pid,
                "hwnd": hwnd,
                "launch_method": launch_method
            }
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Error opening {target}: {str(e)}",
            "failed_command": {"action": "open_application", "target": target}
        }

async def close(target: str) -> Dict[str, Any]:
    """
    Closes an application by name or by focusing on its window.
    Attempts to close gracefully first, then forcefully if needed.
    """
    target_normalized = target.lower().strip()

    try:
        # Find processes matching the target
        matches = []
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if target_normalized in proc.info['name'].lower():
                    matches.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        if not matches:
            return {
                "status": "error",
                "message": f"No running processes found matching '{target}'",
                "failed_command": {"action": "close_application", "target": target}
            }

        # Try to close each matching process gracefully
        closed_count = 0
        for proc in matches:
            try:
                proc.terminate()  # SIGTERM equivalent
                proc.wait(timeout=3)  # Wait for graceful shutdown
                closed_count += 1
            except psutil.TimeoutExpired:
                # Force kill if graceful shutdown failed
                proc.kill()
                closed_count += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass  # Process already gone or no permission

        if closed_count > 0:
            return {
                "status": "success",
                "message": f"Closed {closed_count} instance(s) of {target}",
                "data": {"closed_count": closed_count}
            }
        else:
            return {
                "status": "error",
                "message": f"Failed to close any instances of {target}",
                "failed_command": {"action": "close_application", "target": target}
            }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Error closing {target}: {str(e)}",
            "failed_command": {"action": "close_application", "target": target}
        }