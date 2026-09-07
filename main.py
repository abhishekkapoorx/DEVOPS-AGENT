"""
DEVOPS-AGENT - Main Entry Point

This is the unified entry point for all three implementations.
Choose the implementation that best fits your needs:

1. Modular CompiledSubAgent (RECOMMENDED) - Most robust
2. Basic DeepAgents - Good for prototyping
3. Custom Implementation - Advanced features

Usage:
    python main.py --impl modular "Create a Dockerfile"
    python main.py --impl basic "Create a Dockerfile"
    python main.py --impl custom "Create a Dockerfile"
"""

import sys
import argparse
from loguru import logger

# Configure logging
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
    level="INFO"
)


async def main_async():
    """Async version of main function."""
    parser = argparse.ArgumentParser(
        description="DEVOPS-AGENT - Intelligent DevOps Automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --impl modular "Dockerize my Flask app"
  python main.py --impl basic "Create K8s manifests"
  python main.py --impl custom "Set up AWS infrastructure"
  
Implementations:
  modular  - CompiledSubAgent with existing agents (RECOMMENDED, production-ready)
  custom   - Custom deep agents with reflection (advanced features)
        """
    )
    
    parser.add_argument(
        "--impl",
        choices=["modular", "custom"],
        default="modular",
        help="Implementation to use (default: modular)"
    )
    
    parser.add_argument(
        "--thread-id",
        default="default",
        help="Thread ID for conversation persistence (default: default)"
    )
    
    parser.add_argument(
        "--root-dir",
        default=None,
        help="Root directory for file operations (default: current working directory)"
    )
    
    parser.add_argument(
        "message",
        nargs="?",
        help="Message to send to the agent"
    )
    
    parser.add_argument(
        "--interactive",
        "-i",
        action="store_true",
        help="Start interactive mode"
    )
    
    args = parser.parse_args()
    
    # Display banner
    logger.info("="*60)
    logger.info("🚀 DEVOPS-AGENT - Intelligent DevOps Automation (Async Mode)")
    logger.info("="*60)
    logger.info(f"Implementation: {args.impl}")
    logger.info(f"Thread ID: {args.thread_id}")
    if args.root_dir:
        logger.info(f"Root Directory: {args.root_dir}")
    logger.info("="*60 + "\n")
    
    # Import the appropriate implementation
    if args.impl == "modular":
        from devops_agents.modular import invoke_modular_agent_async
        logger.info("✓ Using Modular CompiledSubAgent with existing agents (RECOMMENDED)")
        logger.info("✓ Running in async mode")
        # Use the async function directly
        invoke_async = invoke_modular_agent_async
    else:  # custom
        from custom import invoke_custom_agent
        # Custom uses different signature - wrap in async
        async def invoke_async(message, thread_id, root_dir=None, stream=False):
            # root_dir ignored for custom implementation
            # stream parameter ignored for custom (not implemented yet)
            import asyncio
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, lambda: invoke_custom_agent(message, session_id=thread_id))
        logger.info("✓ Using Custom Deep Agents")
    
    logger.info("")
    
    # Interactive mode
    if args.interactive or not args.message:
        logger.info("Starting interactive mode (async). Type 'exit' or 'quit' to exit.\n")
        
        while True:
            try:
                message = input("You: ").strip()
                
                if message.lower() in ["exit", "quit", "q"]:
                    logger.info("\nGoodbye! 👋")
                    break
                
                if not message:
                    continue
                
                logger.info("\nAgent: Thinking...\n")
                
                # Pass root_dir if it's the modular implementation
                if args.impl == "modular":
                    result = await invoke_async(message, thread_id=args.thread_id, root_dir=args.root_dir, stream=True)
                else:
                    result = await invoke_async(message, args.thread_id, stream=True)
                
                # Streaming is handled inside invoke, so result is already the final response
                if isinstance(result, dict) and "messages" in result:
                    response = result["messages"][-1].content
                    logger.info(f"Agent: {response}\n")
                else:
                    logger.info(f"Agent: {result}\n")
                
            except KeyboardInterrupt:
                logger.info("\n\nGoodbye! 👋")
                break
            except Exception as e:
                logger.error(f"Error: {e}")
                import traceback
                traceback.print_exc()
    
    # Single message mode
    else:
        logger.info(f"User: {args.message}\n")
        logger.info("Agent: Thinking...\n")
        
        try:
            # Pass root_dir if it's the modular implementation
            if args.impl == "modular":
                result = await invoke_async(args.message, thread_id=args.thread_id, root_dir=args.root_dir, stream=True)
            else:
                result = await invoke_async(args.message, args.thread_id, stream=True)
            
            # Streaming is handled inside invoke, so result is already the final response
            if isinstance(result, dict) and "messages" in result:
                response = result["messages"][-1].content
                logger.info(f"Agent: {response}\n")
            else:
                logger.info(f"Agent: {result}\n")
            logger.info("="*60)
            
        except Exception as e:
            logger.error(f"Error: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)


def main():
    """Main entry point - runs async main in event loop."""
    import asyncio
    asyncio.run(main_async())


if __name__ == "__main__":
    main()

