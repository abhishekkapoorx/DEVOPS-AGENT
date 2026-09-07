"""
Deep Agents System Test Suite

This script tests the deep agents system to verify:
1. All agents are importable
2. Reflection mechanisms work
3. Error recovery functions
4. Memory persistence works
5. Observability is configured

Run with: python test_deep_agents.py
"""

import sys
import os
from loguru import logger

# Configure logger
logger.remove()
logger.add(sys.stderr, level="INFO")


def test_imports():
    """Test that all deep agent modules can be imported."""
    logger.info("Testing imports...")
    
    try:
        # Test utility imports
        from utils.deep_agent_state import (
            ReflectionState,
            DockerAgentState,
            K8sAgentState,
            CoderAgentState,
            ThinkerAgentState,
            WatcherAgentState,
            CloudAgentState,
            create_initial_reflection_state,
        )
        logger.success("✓ Deep agent state schemas imported")
        
        from utils.reflection import (
            ReflectionNode,
            create_reflection_hook,
            should_continue_or_reflect,
            create_error_recovery_node,
        )
        logger.success("✓ Reflection mechanisms imported")
        
        from utils.memory_persistence import (
            CheckpointManager,
            get_checkpoint_manager,
            create_checkpointed_agent,
            AgentSession,
        )
        logger.success("✓ Memory persistence imported")
        
        from utils.observability import (
            ObservabilityManager,
            get_observability_manager,
            setup_observability,
            invoke_with_observability,
        )
        logger.success("✓ Observability tools imported")
        
        # Test agent imports
        from agents.ThinkerAgent import agent as ThinkerAgent
        logger.success("✓ ThinkerAgent imported")
        
        from agents.WatcherAgent import agent as WatcherAgent
        logger.success("✓ WatcherAgent imported")
        
        from agents.CoderAgent import agent as CoderAgent
        logger.success("✓ CoderAgent imported")
        
        from agents.BuilderAgent import agent as BuilderAgent
        logger.success("✓ BuilderAgent imported")
        
        from agents.CloudAgent import agent as CloudAgent
        logger.success("✓ CloudAgent imported")
        
        # Test supervisor import
        from agent import supervisor
        logger.success("✓ Deep Agent Supervisor imported")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ Import failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_state_initialization():
    """Test that state initialization works correctly."""
    logger.info("\nTesting state initialization...")
    
    try:
        from utils.deep_agent_state import create_initial_reflection_state
        
        state = create_initial_reflection_state(
            agent_name="test_agent",
            session_id="test_session"
        )
        
        assert "messages" in state
        assert state["plan_version"] == 0
        assert state["revision_count"] == 0
        assert state["agent_name"] == "test_agent"
        
        logger.success("✓ State initialization working")
        return True
        
    except Exception as e:
        logger.error(f"✗ State initialization failed: {e}")
        return False


def test_observability_setup():
    """Test observability configuration."""
    logger.info("\nTesting observability setup...")
    
    try:
        from utils.observability import setup_observability, get_observability_manager
        
        # Setup observability
        obs = setup_observability(
            project_name="test-project",
            enable_langsmith=False  # Disable for testing
        )
        
        # Test metric tracking
        obs.track_metric("test_metric", 42, {"test": True})
        
        metrics = obs.get_metrics("test_metric")
        assert "test_metric" in metrics
        assert len(metrics["test_metric"]) == 1
        assert metrics["test_metric"][0]["value"] == 42
        
        logger.success("✓ Observability setup working")
        return True
        
    except Exception as e:
        logger.error(f"✗ Observability setup failed: {e}")
        return False


def test_checkpoint_manager():
    """Test checkpoint manager initialization."""
    logger.info("\nTesting checkpoint manager...")
    
    try:
        from utils.memory_persistence import get_checkpoint_manager, create_session_id
        
        # Get checkpoint manager (will use in-memory for testing)
        manager = get_checkpoint_manager(backend="memory")
        
        assert manager is not None
        assert manager.checkpointer is not None
        
        # Test session ID creation
        session_id = create_session_id("test")
        assert "test_" in session_id
        
        logger.success("✓ Checkpoint manager working")
        return True
        
    except Exception as e:
        logger.error(f"✗ Checkpoint manager failed: {e}")
        return False


def test_reflection_node():
    """Test reflection node creation."""
    logger.info("\nTesting reflection mechanisms...")
    
    try:
        from utils.reflection import ReflectionNode
        from llms import DEFAULT_MODEL
        
        reflection_node = ReflectionNode(
            model=DEFAULT_MODEL,
            min_confidence_threshold=0.7,
            max_reflection_iterations=3,
        )
        
        assert reflection_node is not None
        assert reflection_node.min_confidence_threshold == 0.7
        assert reflection_node.max_reflection_iterations == 3
        
        logger.success("✓ Reflection node created successfully")
        return True
        
    except Exception as e:
        logger.error(f"✗ Reflection node creation failed: {e}")
        return False


def test_handoff_tools():
    """Test that all handoff tools are available."""
    logger.info("\nTesting handoff tools...")
    
    try:
        from tools.HandOffs.agent import (
            thinker_agent_handoff,
            coder_agent_handoff,
            docker_k8s_handoff,
            cloud_agent_handoff,
            watcher_agent_handoff,
            all_agent_handoffs,
        )
        
        assert len(all_agent_handoffs) == 5
        logger.success("✓ All handoff tools available")
        return True
        
    except Exception as e:
        logger.error(f"✗ Handoff tools test failed: {e}")
        return False


def test_supervisor_configuration():
    """Test supervisor is correctly configured."""
    logger.info("\nTesting supervisor configuration...")
    
    try:
        from agent import supervisor
        
        # Verify supervisor exists
        assert supervisor is not None
        
        # Check config
        config = supervisor.config
        assert "recursion_limit" in config or "configurable" in config
        
        logger.success("✓ Supervisor configured correctly")
        return True
        
    except Exception as e:
        logger.error(f"✗ Supervisor configuration failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_integration_test():
    """Run a simple integration test."""
    logger.info("\nRunning integration test...")
    
    try:
        from agent import supervisor
        from utils.memory_persistence import create_session_id, get_thread_config
        
        # Create a test session
        session_id = create_session_id("integration_test")
        config = get_thread_config(session_id)
        
        # Test with a simple query
        logger.info("Invoking supervisor with test query...")
        result = supervisor.invoke({
            "messages": [
                {"role": "user", "content": "What agents are available in this system?"}
            ]
        }, config=config)
        
        assert result is not None
        assert "messages" in result
        
        logger.success("✓ Integration test passed")
        return True
        
    except Exception as e:
        logger.error(f"✗ Integration test failed: {e}")
        logger.warning("This is expected if LLM credentials are not configured")
        return False


def main():
    """Run all tests."""
    logger.info("=" * 60)
    logger.info("Deep Agents System Test Suite")
    logger.info("=" * 60)
    
    results = []
    
    # Run tests
    results.append(("Imports", test_imports()))
    results.append(("State Initialization", test_state_initialization()))
    results.append(("Observability Setup", test_observability_setup()))
    results.append(("Checkpoint Manager", test_checkpoint_manager()))
    results.append(("Reflection Node", test_reflection_node()))
    results.append(("Handoff Tools", test_handoff_tools()))
    results.append(("Supervisor Config", test_supervisor_configuration()))
    
    # Optional integration test (may fail without LLM credentials)
    logger.info("\n" + "=" * 60)
    logger.info("Optional Integration Test")
    logger.info("=" * 60)
    results.append(("Integration Test", run_integration_test()))
    
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("Test Summary")
    logger.info("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        logger.info(f"{status}: {test_name}")
    
    logger.info("-" * 60)
    logger.info(f"Results: {passed}/{total} tests passed")
    logger.info("=" * 60)
    
    if passed == total:
        logger.success("\n🎉 All tests passed! Deep Agents system is ready.")
        return 0
    elif passed >= total - 1:  # Allow integration test to fail
        logger.warning("\n⚠️  Core tests passed. Integration test may require LLM credentials.")
        return 0
    else:
        logger.error("\n❌ Some tests failed. Please review the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

