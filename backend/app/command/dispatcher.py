from .schema import Command, ActionType
from .exceptions import DispatchError
from ..tools import applications, browser, keyboard, mouse, web_reader
from ..session.tracker import session_state
from typing import Dict,Any
import asyncio
def _make_browser_placeholder(action: ActionType):
    async def _placeholder(target: str) -> Dict[str, Any]:
        return {
            "status": "error",
            "message": f"Action {action.value} is not implemented yet. "
                       f"This is a placeholder for future browser automation.",
            "failed_command": {
                "action": action.value,
                "target": target
            }
        }
    return _placeholder
async def dispatch_command(command: Command) -> dict:
    """
    Dispatches a single command to the appropriate tool and updates session state.

    Args:
        command: Validated Command object (action from ActionType enum, target string)

    Returns:
        Dictionary with execution result: {"status": "success"/"error", "data": ..., "message": "..."}
    """
    try:
        # Handle browser UI actions via web_reader and existing mouse/keyboard helpers.
        if command.action in (ActionType.BROWSER_CLICK, ActionType.BROWSER_TYPE, ActionType.BROWSER_PRESS, ActionType.LIST_ITEM):
              # Use web_reader to locate the target element if needed.
              if command.action == ActionType.LIST_ITEM:
                elem = await web_reader.inspect_list_item(command.target)

                if not elem:
                    return {
                        "status": "error",
                        "message": f"Could not locate item for target '{command.target}'",
                        "failed_command": command.dict()
                    }
              elif command.action == ActionType.BROWSER_PRESS:
                  # browser_press just presses a key — no element lookup needed
                  elem = None
              else:
                  # For click or type actions we need element coordinates.
                #   await asyncio.sleep(1)
                  matches = await web_reader.inspect([command.target])
                  print("ALL MATCHES:", matches)
                  if not matches:
                      return {
                          "status": "error",
                          "message": f"Could not locate element for target '{command.target}'",
                          "failed_command": command.dict()
                      }
                  # Pick the best match (first in list)
                  elem = matches[0]
                  print("WEB READER MATCH:", elem)
                  x, y, width, height = elem.get("x"), elem.get("y"), elem.get("width"), elem.get("height")
                  if None in (x, y, width, height):
                      return {
                          "status": "error",
                          "message": f"Target element for '{command.target}' lacks bounding box information.",
                          "failed_command": command.dict()
                      }
                  center_x = x + width // 2
                  center_y = y + height // 2

              # Bring the browser to foreground to ensure visibility.
              await browser._bring_browser_to_foreground()
              page = await browser.get_current_page()

              if command.action == ActionType.BROWSER_CLICK:
                  clicked = False
                  if page:
                      try:
                          sel = elem.get("selector")
                          if sel:
                              await page.click(sel, timeout=3000)
                              clicked = True
                          else:
                              await page.mouse.click(center_x, center_y)
                              clicked = True
                      except Exception as pe:
                          print(f"Playwright click error: {pe}, falling back to mouse.click")
                  if not clicked:
                      result = await mouse.click(f"{center_x},{center_y}")
                  else:
                      result = {
                          "status": "success",
                          "message": f"Clicked {command.target}",
                          "data": {"selector": elem.get("selector"), "x": center_x, "y": center_y}
                      }

              elif command.action == ActionType.BROWSER_TYPE:
                  typed = False
                  if page:
                      try:
                          sel = elem.get("selector")
                          if sel:
                              await page.click(sel, timeout=3000)
                              await page.fill(sel, command.value or "")
                              typed = True
                          else:
                              await page.mouse.click(center_x, center_y)
                              await page.keyboard.type(command.value or "")
                              typed = True
                      except Exception as pe:
                          print(f"Playwright type error: {pe}, falling back to mouse/keyboard")
                  if not typed:
                      click_res = await mouse.click(f"{center_x},{center_y}")
                      if click_res.get("status") == "error":
                          return click_res
                      result = await keyboard.type_text(command.value)
                  else:
                      result = {
                          "status": "success",
                          "message": f"Typed '{command.value}' into {command.target}",
                          "data": {"target": command.target, "value": command.value}
                      }

              elif command.action == ActionType.BROWSER_PRESS:
                  pressed = False
                  if page:
                      try:
                          press_res = await browser.browser_press(command.target)
                          if press_res.get("status") == "success":
                              pressed = True
                      except Exception as pe:
                          print(f"Playwright press error: {pe}, falling back to keyboard.press_key")
                  if not pressed:
                      result = await keyboard.press_key(command.target)
                  else:
                      result = {
                          "status": "success",
                          "message": f"Pressed {command.target}",
                          "data": {"key": command.target}
                      }

              elif command.action == ActionType.LIST_ITEM:
                try:
                    await elem.scroll_into_view_if_needed()
                    await elem.click()
                    await asyncio.sleep(1)
                    result = {
                        "status": "success",
                        "message": f"Clicked list item {command.target} with Playwright."
                    }
                except Exception as e:
                    result = {
                        "status": "error",
                        "message": f"Playwright failed to click list item: {str(e)}",
                        "failed_command": command.dict()
                    }
              else:  # pragma: no cover
                  result = {"status": "error", "message": "Unsupported browser action", "failed_command": command.dict()}

              if result.get("status") == "success":
                  await session_state.update_after_command(command, result)
              return result

        # For non-browser actions use the existing tool map.
        tool_map = {
            ActionType.OPENAPPLICATION: applications.open,
            ActionType.OPENWEBSITE: browser.open,
            ActionType.CLOSEAPPLICATION: applications.close,
            ActionType.SEARCH: browser.search,
            ActionType.TYPE: keyboard.type_text,
            ActionType.CLICK: mouse.click,
            ActionType.PRESSKEY: keyboard.press_key,
            ActionType.WAIT: browser.wait,
            # Still keep placeholders for future actions.
            ActionType.BROWSER_CLICK: None,
            ActionType.BROWSER_TYPE: None,
            ActionType.BROWSER_PRESS: None,
        }

        tool_func = tool_map.get(command.action)
        if not tool_func:
            return {
                "status": "error",
                "message": f"Unsupported action: {command.action.value}",
                "failed_command": command.dict()
            }

        # Execute the tool function (all tools are async)
        if command.action == ActionType.TYPE:
            result = await tool_func(command.value or "")
        else:
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
        
async def dispatch_plan(plan):
    results = []

    browser_actions = {
        ActionType.OPENWEBSITE,
        ActionType.SEARCH,
        ActionType.BROWSER_CLICK,
        ActionType.BROWSER_TYPE,
        ActionType.BROWSER_PRESS,
        ActionType.LIST_ITEM,
    }

    has_browser_action = any(
        command.action in browser_actions
        for command in plan.commands
    )

    if has_browser_action:
        browser._current_command_page = await browser._get_page_for_command()

    try:
        for command in plan.commands:
            result = await dispatch_command(command)
            results.append(result)

            if result.get("status") == "error":
                break
    finally:
        browser._current_command_page = None

    return results