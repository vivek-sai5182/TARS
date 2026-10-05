import os
import json
from typing import Dict

from google import genai
from google.genai import types
from groq import Groq
from ..command.schema import CommandPlan, ActionType
from ..command.exceptions import InvalidCommandPlanError
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]

load_dotenv(BASE_DIR / ".env")

# Load environment variables (loaded by main.py using python-dotenv)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GROQ_API_KEY = os.getenv("Groq_key")

if not GEMINI_API_KEY:

    raise RuntimeError(
        "GEMINI_API_KEY is not set. Please check your backend/.env file."
    )

if not GROQ_API_KEY:
    raise RuntimeError(
        "Groq_key is not set. Please check your backend/.env file."
    )


# Configure the Gemini client
client = genai.Client(api_key=GEMINI_API_KEY)
groq_client = Groq(api_key=GROQ_API_KEY)

def _build_prompt(user_input: str, session_context: str) -> str:
    """
    Builds the prompt for Gemini, including system instructions and context.
    The prompt is designed to elicit ONLY valid JSON matching CommandPlan schema.
    """

    # Define the allowed actions as a comma-separated string for the prompt
    allowed_actions = ", ".join(
        [f'"{action.value}"' for action in ActionType]
    )

    prompt = f"""
You are the planning module of TARS, a Windows desktop AI assistant.
Your job is to convert the user's natural-language task into an exact sequence of actions that TARS can execute.

You MUST output ONLY valid JSON matching the provided schema.
NEVER output text outside the JSON.
NEVER explain your reasoning.
NEVER invent new actions.

ALLOWED ACTIONS (you must use these exact strings):
{allowed_actions}
and use case of each action

1. open_application
   Opens a Windows application.
   Use this when the user wants to launch an application such as Brave, Notepad, settings or any windows executable apps.

2. open_website
   Opens a website directly in the default browser.
   Use this for the initial website/application entry point.
   Example: "open YouTube" → open_website with target "youtube.com"

3. close_application
   Closes a Windows application.
   Use this when the user explicitly asks to close an application.

4. search
   Performs a general web search in browser.
   Use this only when the user wants to search the web itself, not when searching inside an already opened website.

5. type
   Types text into a desktop application like notepad.
   Use this for normal Windows application text input not to type inside an opened website.

6. click
   Performs a mouse click on a desktop application element.

7. press_key
   Presses a keyboard key in a desktop application.
   Example: Enter, Escape, Tab, ctrl, etc.

8. wait
   Waits for a specified amount of time before continuing.

9. browser_click
    Clicks an element inside the webpage.
    Use this for buttons, links, menus, search boxes, etc.

10. browser_type
    Types text into an element inside the webpage mostly for searching and for mail writing purposes.
    The target identifies the webpage element and the value contains the text to type.

11. browser_press
    Presses a keyboard key inside the webpage.
    Example: pressing Enter after entering a search query.
12. list_item
    Selects an item from a rendered list by its position number.
    Example: selecting the 1st video uses target "1", the 2nd product uses target "2".
    
OUTPUT FORMAT (must match exactly):
{{
    "commands": [
    {{
      "action": "<one of the allowed actions above>",
      "target": "<string describing the where to do action>",
      "value": "<optional string - only used for browser actions like browser_type, browser_press>"
    }}
  ]

}}

EXAMPLE 1:
User: Open YouTube and search for Telugu songs and click on 1st video.

Output:

{{
  "commands": [
    {{
      "action": "open_website",
      "target": "youtube.com",
      "value": ""
    }},
    {{
      "action": "browser_type",
      "target": "searchbar",
      "value": "Telugu songs"
    }},
    {{
      "action": "browser_press",
      "target": "Enter",
      "value": ""
    }},
    {{
      "action": "list_item",
      "target": "1",
      "value": ""
    }}
  ]
}}
EXAMPLE 2:

User: Open Gmail and write a leave mail to name@dm.com.

Output:
{{
  "commands": [
    {{
      "action": "open_website",
      "target": "gmail.com",
      "value": ""
    }},
    {{
      "action": "browser_click",
      "target": "Compose",
      "value": ""
    }},
    {{
      "action": "browser_type",
      "target": "To",
      "value": "name@dm.com"
    }},
    {{
      "action": "browser_type",
      "target": "Subject",
      "value": "Leave Request"
    }},
    {{
      "action": "browser_type",
      "target": "Message",
      "value": "Dear Sir/Madam,\nI am writing to request leave due to personal reasons.\nI kindly request you to grant me leave for the required period.\nThank you for your consideration.\nRegards"
    }}
  ]
}}

TASK STRUCTURE:
Every user task should be understood as two possible parts:

PART 1 — OPENING:
Determine what application or website must be opened first.

PART 2 — NAVIGATION:
Determine what must be done inside the opened application or website to complete the user's request.

For website-based tasks, PART 2 is especially important. Do not stop after opening the website. Convert the user's requested navigation and interaction into the appropriate browser actions.
RULES:
1. If the user input is ambiguous or unclear, output the minimal valid plan (e.g., a wait command).
2. If the user asks for something impossible with the allowed actions, output a wait command.
3. User may have typos - interpret intelligently but stay within the allowed actions.
4. Use the session context to resolve pronouns and implicit references.
5. if user asks to write something, generate the content yourself and put the generated content in the appropriate "value" field.normally 3 or 4 lines enough as shown in above examples.
6. If unsure whether a search should be general web or in-site, default to general web search.
7. Decide intelligently and logically which action to use like you yourself are doing that task.
8. When the user wants to search inside a specific website:
   - First open the website with open_website.
   - Use browser_type to enter the search query into the website's searchbar.
   - Use browser_press with target "Enter".
   - Do NOT use the general search action.
   
CURRENT SESSION CONTEXT:
{session_context}

USER INPUT:
"{user_input}"

YOUR RESPONSE (must be ONLY the JSON object, no extra text):
"""

    return prompt.strip()


def plan_command(user_input: str, session_context: str) -> CommandPlan:
    """
    Plans a command sequence using Groq first, with Gemini as fallback.
    """

    try:
        prompt = _build_prompt(user_input, session_context)

        # Try Groq first
        try:
            response = groq_client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.1,
                max_tokens=1024,
            )

            response_text = response.choices[0].message.content.strip()

        except Exception as groq_error:
            print(f"GROQ ERROR: {groq_error}")


            # Fall back to Gemini
            response = client.models.generate_content(
                model="gemini-3.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    top_p=0.8,
                    top_k=20,
                    max_output_tokens=1024,
                ),
            )

            response_text = response.text.strip()

        # Clean up potential markdown formatting
        if response_text.startswith("```json"):
            response_text = response_text[7:]

        if response_text.endswith("```"):
            response_text = response_text[:-3]

        response_text = response_text.strip()

        # Parse JSON
        try:
            parsed_json = json.loads(response_text)

        except json.JSONDecodeError as e:
            raise InvalidCommandPlanError(
                f"AI output is not valid JSON. Error: {str(e)}. "
                f"Output was: {response_text[:200]}..."
            )

        # Validate against CommandPlan schema
        validated_plan = CommandPlan(**parsed_json)

        return validated_plan

    except InvalidCommandPlanError:
        raise

    except Exception as e:
        raise InvalidCommandPlanError(
            f"Failed to plan command: {str(e)}"
        )