import asyncio
from langchain_core.messages import HumanMessage
from agents.BuilderAgent.DockerAgent import agent as docker_agent
from utils.context import create_context

async def test_docker_agent():
    input = {"messages": [HumanMessage(content="create dockerfile for /home/invincible/projects/DEVOPS-AGENT/dummy_projects/harmonia_flask")]}
    
    # Create proper context for the agent
    context = create_context(
        working_directory="/home/invincible/projects/DEVOPS-AGENT/dummy_projects/harmonia_flask",
        project_root="/home/invincible/projects/DEVOPS-AGENT/dummy_projects/harmonia_flask"
    )
    
    # Pass context in config
    config = {
        "configurable": {
            "context": context
        }
    }
    
    async for chunk in docker_agent.astream(input, config=config):
        print(chunk)
        assert chunk is not None
        # assert "Dockerfile" in chunk

if __name__ == "__main__":
    asyncio.run(test_docker_agent())