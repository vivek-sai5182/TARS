from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from .planner.gemini_planner import plan_command
from .command.dispatcher import dispatch_plan
from .command.schema import CommandPlan
from .command.validator import validate_gemini_output, InvalidCommandPlanError
from .session.tracker import session_state
from dotenv import load_dotenv

load_dotenv()
app = FastAPI(title="TARS Backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class CommandRequest(BaseModel):
    command: str

@app.get("/")
def root():
    return {
        "status": "online",
        "message": "TARS backend is running"
    }

@app.post("/command")
async def execute_natural_language(request: CommandRequest):
    """
    Endpoint to process natural language commands.
    Flow:
    1. Get user input (natural language)
    2. Plan commands using Gemini (with session context)
    3. Validate Gemini output against schema
    4. Dispatch commands to tools
    5. Update session state after execution
    6. Return structured results
    """
    user_input = request.command.strip()
    if not user_input:
        raise HTTPException(status_code=400, detail="Empty command")

    try:
        # Step 1: Plan commands using Gemini (with current session state)
        # Note: gemini_planner.plan_command returns a CommandPlan object
        command_plan: CommandPlan = plan_command(
            user_input=user_input,
            session_context=session_state.get_context_summary()
        )

        # Step 2: Validate the plan (double-check against schema)
        # Note: plan_command should already return valid CommandPlan, but we validate again for safety
        validated_plan = validate_gemini_output(command_plan.dict())

        # Step 3: Dispatch the validated plan to tools
        execution_results = await dispatch_plan(validated_plan)

        # Step 4: Update session state after command execution
        # Note: dispatcher updates state after each command, but we refresh context here
        # session_state.update_context()

        return {
            "status": "success",
            "input": user_input,
            "plan": validated_plan.dict(),
            "results": execution_results
        }

    except InvalidCommandPlanError as e:
        # Handle validation errors (Gemini output doesn't match schema)
        raise HTTPException(
            status_code=422,
            detail={
                "error": "Invalid command plan from AI",
                "message": str(e),
                "user_input": user_input
            }
        )
    except Exception as e:
        # Handle all other errors (planner, dispatcher, tools, etc.)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Internal processing error",
                "message": str(e),
                "user_input": user_input
            }
        )