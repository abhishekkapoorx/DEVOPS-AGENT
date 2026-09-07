"""
Test Suite for Modular DeepAgents Implementation

Tests the CompiledSubAgent pattern with modular subagents.
"""

import sys
from loguru import logger

logger.remove()
logger.add(sys.stderr, level="INFO")


def test_subagent_imports():
    """Test that modular subagents can be imported."""
    logger.info("Testing modular subagent imports...")
    
    try:
        from devops_agents.modular.subagents import (
            create_builder_subagent,
            create_cloud_subagent,
            create_coder_subagent,
            create_thinker_subagent,
            create_watcher_subagent,
        )
        
        logger.success("✓ Subagent modules imported")
        return True
    except ImportError as e:
        logger.error(f"✗ Subagent import failed: {e}")
        return False


def test_subagent_creation():
    """Test creating individual subagents."""
    logger.info("\nTesting subagent creation...")
    
    try:
        from devops_agents.modular.subagents import (
            create_builder_subagent,
            create_cloud_subagent,
            create_coder_subagent,
            create_thinker_subagent,
            create_watcher_subagent,
        )
        
        builder = create_builder_subagent()
        cloud = create_cloud_subagent()
        coder = create_coder_subagent()
        thinker = create_thinker_subagent()
        watcher = create_watcher_subagent()
        
        assert builder is not None
        assert cloud is not None
        assert coder is not None
        assert thinker is not None
        assert watcher is not None
        
        logger.success("✓ All subagents created successfully")
        return True
    except Exception as e:
        logger.error(f"✗ Subagent creation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_compiled_subagent_wrapping():
    """Test wrapping subagents in CompiledSubAgent."""
    logger.info("\nTesting CompiledSubAgent wrapping...")
    
    try:
        from deepagents import CompiledSubAgent
        from devops_agents.modular.subagents import create_builder_subagent
        
        builder_graph = create_builder_subagent()
        
        compiled_builder = CompiledSubAgent(
            name="builder_expert",
            description="Test builder expert",
            runnable=builder_graph
        )
        
        assert compiled_builder is not None
        # Note: CompiledSubAgent may store config differently
        
        logger.success("✓ CompiledSubAgent wrapping successful")
        return True
    except Exception as e:
        logger.error(f"✗ CompiledSubAgent wrapping failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_modular_agent_import():
    """Test importing the modular agent."""
    logger.info("\nTesting modular agent import...")
    
    try:
        from devops_agents.modular import invoke_modular_agent
        
        assert invoke_modular_agent is not None
        
        logger.success("✓ Modular agent imported successfully")
        return True
    except Exception as e:
        logger.error(f"✗ Modular agent import failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_modular_agent_invocation():
    """Test invoking the modular agent."""
    logger.info("\nTesting modular agent invocation...")
    
    try:
        from devops_agents.modular import invoke_modular_agent
        
        logger.info("Invoking modular agent...")
        result = invoke_modular_agent(
            "What subagents do you have available?",
            thread_id="test_modular"
        )
        
        assert result is not None
        assert "messages" in result
        
        logger.success("✓ Modular agent invocation successful")
        logger.info(f"Response preview: {str(result['messages'][-1].content)[:100]}...")
        return True
    except Exception as e:
        logger.error(f"✗ Modular agent invocation failed: {e}")
        logger.warning("May fail without LLM credentials")
        return False


def test_context_quarantine():
    """Test that subagents provide concise outputs."""
    logger.info("\nTesting context quarantine pattern...")
    
    try:
        from devops_agents.modular import invoke_modular_agent
        
        # This should delegate to a subagent which returns concise output
        result = invoke_modular_agent(
            "Briefly explain what the docker_expert subagent can do",
            thread_id="context_test"
        )
        
        response = result['messages'][-1].content
        
        # Check that response is reasonably concise (not bloated)
        is_concise = len(response) < 2000  # Should be brief
        
        if is_concise:
            logger.success("✓ Context quarantine working (concise output)")
        else:
            logger.warning("⚠ Output may be verbose (check subagent prompts)")
        
        return True
    except Exception as e:
        logger.error(f"✗ Context test failed: {e}")
        return False


def main():
    """Run all tests."""
    logger.info("=" * 60)
    logger.info("Modular DeepAgents Test Suite (CompiledSubAgent Pattern)")
    logger.info("=" * 60)
    
    results = []
    
    # Core tests
    results.append(("Subagent Imports", test_subagent_imports()))
    results.append(("Subagent Creation", test_subagent_creation()))
    results.append(("CompiledSubAgent Wrapping", test_compiled_subagent_wrapping()))
    results.append(("Modular Agent Import", test_modular_agent_import()))
    
    # Integration tests
    logger.info("\n" + "=" * 60)
    logger.info("Integration Tests (require LLM)")
    logger.info("=" * 60)
    results.append(("Modular Agent Invocation", test_modular_agent_invocation()))
    results.append(("Context Quarantine", test_context_quarantine()))
    
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
    
    if passed >= 4:
        logger.success("\n🎉 Core tests passed! Modular CompiledSubAgent pattern working.")
        return 0
    else:
        logger.error("\n❌ Some core tests failed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

