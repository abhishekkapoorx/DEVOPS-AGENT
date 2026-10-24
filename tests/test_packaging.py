import re
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _requirement_names(lines):
    return {
        match.group(1).lower().replace("_", "-")
        for line in lines
        if (match := re.match(r"\s*([A-Za-z0-9_.-]+)", line))
    }


def test_server_extra_covers_server_requirements_and_ci_installs_it():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    server_extra = _requirement_names(project["project"]["optional-dependencies"]["server"])
    server_requirements = _requirement_names(
        (ROOT / "requirements-server.txt").read_text(encoding="utf-8").splitlines()
    )
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert server_requirements <= server_extra
    assert {"argon2-cffi", "fastapi", "sqlalchemy", "langchain-core"} <= server_extra
    assert '".[cli,server,test]"' in workflow
