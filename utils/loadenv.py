import getpass
import os

from dotenv import load_dotenv

load_dotenv()

def _set_if_undefined(var: str):
    if not os.environ.get(var):
        os.environ[var] = getpass.getpass(f"Please provide your {var}")
        
def _sanitize_path(path: str) -> str:
    # Strip surrounding quotes and normalize
    cleaned = path.strip().strip('"').strip("'")
    cleaned = os.path.expandvars(os.path.expanduser(cleaned))
    return os.path.abspath(os.path.normpath(cleaned))


def _get_project_root_from_env() -> str:
    env_val = os.getenv("PROJECT_ROOT")
    if env_val:
        candidate = _sanitize_path(env_val)
        if os.path.isdir(candidate):
            return candidate
    # Non-blocking fallback to current directory without calling os.getcwd()
    return "."