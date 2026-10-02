import subprocess


def execute_command(command: str):
    command = command.lower().strip()

    applications = {
        "open notepad": "notepad.exe",
        "open calculator": "calc.exe",
    }

    if command in applications:
        subprocess.Popen(applications[command])

        return {
            "status": "success",
            "message": f"Opened {command.replace('open ', '')}"
        }

    return {
        "status": "error",
        "message": "Command not recognized"
    }