import subprocess
from langchain_core.tools import tool

@tool
def run_windows_command(command: str) -> str:
    """Execute a Windows command and return the output.
    
    Args:
        command (str): The Windows command to execute. Can include shell commands, 
                      batch files, PowerShell commands, or any executable available 
                      in the system PATH. Examples: 'dir', 'echo hello', 'python script.py'
    
    Returns:
        str: The command output (stdout) if successful, or error message (stderr) 
             if the command fails. Returns "Error: <exception_message>" if an 
             exception occurs during execution.
    """
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        return result.stdout if result.stdout else result.stderr
    except Exception as e:
        return f"Error: {str(e)}"

import subprocess
from langchain_core.tools import tool

@tool
def run_windows_command(command: str) -> str:
    """Execute a Windows command and return the output.
    
    Args:
        command (str): The Windows command to execute. Can include shell commands, 
                      batch files, PowerShell commands, or any executable available 
                      in the system PATH. Examples: 'dir', 'echo hello', 'python script.py'
    
    Returns:
        str: The command output (stdout) if successful, or error message (stderr) 
             if the command fails. Returns "Error: <exception_message>" if an 
             exception occurs during execution.
    """
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        return result.stdout if result.stdout else result.stderr
    except Exception as e:
        return f"Error: {str(e)}"