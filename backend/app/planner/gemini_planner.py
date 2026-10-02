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
You are TARS' command planner. Your ONLY job is to convert natural language into a structured command plan.

You MUST output ONLY valid JSON matching the provided schema.
NEVER output text outside the JSON.
NEVER explain your reasoning.
NEVER invent new actions.

ALLOWED ACTIONS (you must use these exact strings):
{allowed_actions}

OUTPUT FORMAT (must match exactly):
{{
"commands": [
    {{
    "action": "<one of the allowed actions above>",
    "target": "<string describing the target>"
    }}
]
}}

RULES:
1. If the user input is ambiguous or unclear, output the minimal valid plan (e.g., a wait command).
2. If the user asks for something impossible with the allowed actions, output a wait command.
3. User may have typos - interpret intelligently but stay within the allowed actions.
4. Use the session context to resolve pronouns and implicit references.
5. If the user asks to search for something on a website, use the "search" action for the search term. Do NOT use "type" or "press_key" to perform a website search.
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