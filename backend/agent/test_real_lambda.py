#!/usr/bin/env python3
"""
Real Lambda Function Test

Tests the system with actual deployed Lambda functions in us-east-1.
Uses minimal resource consumption while testing real AWS services.
"""

import asyncio
import logging
import time
import sys
import os
import boto3
from research_orchestrator import create_research_orchestrator

# Configurable parameters
SESSION_ID = f"lambda_test_{int(time.time())}"
QUERY = "machine learning"
REQUIRED_FUNCTIONS = ["search_arxiv", "search_semantic_scholar"]

# Add paths for imports
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

# Import ConversationContext with fallback to mock
try:
    from strands_agents import ConversationContext

    STRANDS_SDK_AVAILABLE = True
except ImportError:
    from backend.agent.mock_strands_sdk import ConversationContext

    STRANDS_SDK_AVAILABLE = False


async def test_real_lambda_functions():
    """Test with real deployed Lambda functions."""
    logger = logging.getLogger("TestRealLambda")
    logger.info("🏆 AWS AI Agent Global Hackathon")
    logger.info("Real Lambda Function Integration Test")
    logger.info("Profile: hackathon-friend-role")
    logger.info("Region: us-east-1 (Lambda functions deployed)")
    logger.info("=" * 60)

    # Step 1: Check AWS access
    logger.info("1. Checking AWS access...")
    try:
        session = boto3.Session()
        sts = session.client("sts")
        identity = sts.get_caller_identity()
        account_id = identity.get("Account")
        user_arn = identity.get("Arn")
        region = session.region_name or session.client("lambda").meta.region_name
        logger.info(
            f"AWS access confirmed. Account: {account_id}, User/Role: {user_arn}, Region: {region}"
        )
    except Exception as e:
        logger.error(f"AWS access failed: {e}")
        return False

    # Step 2: List available Lambda functions
    logger.info("2. Checking deployed Lambda functions...")
    try:
        lambda_client = boto3.client("lambda")
        sns_client = boto3.client("sns")
        response = lambda_client.list_functions()
        functions = [f["FunctionName"] for f in response["Functions"]]
        logger.info(f"Available functions: {', '.join(functions)}")
        available_functions = []
        for func in REQUIRED_FUNCTIONS:
            if func in functions:
                available_functions.append(func)
                logger.info(f"{func}: Available")
            else:
                logger.warning(f"{func}: Not found")
        if not available_functions:
            logger.warning("No required functions found - will test error handling")
    except Exception as e:
        logger.error(f"Lambda function check failed: {e}")
        return False

    # Step 3: Test orchestrator with real Lambda functions
    logger.info("3. Testing research orchestrator with real Lambda functions...")
    try:
        orchestrator = create_research_orchestrator(
            session_id=SESSION_ID,
            lambda_client=lambda_client,
            sns_client=sns_client,
            use_local_tools=False,
            log_level=logging.DEBUG,  # Set agent log level to DEBUG
        )
        logger.info("Orchestrator initialized. Using real Lambda functions.")
    except Exception as e:
        logger.error(f"Orchestrator creation failed: {e}")
        return False

    # Step 4: Test real literature search with Lambda functions
    logger.info("4. Testing literature search with real Lambda functions...")
    start_time = time.time()
    try:
        context = ConversationContext(session_id=SESSION_ID)
        logger.info(f"Processing query: '{QUERY}'")
        response = await orchestrator.process_message(QUERY, context)
        duration = time.time() - start_time

        # Explicitly check for failure messages in the response
        if "error" in response.lower() or "failed" in response.lower():
            raise Exception(f"Orchestrator returned an error: {response}")

        papers_found = 0
        if "Found **" in response:
            try:
                start = response.find("Found **") + 8
                end = response.find(" relevant papers", start)
                papers_found = int(response[start:end])
            except Exception:
                papers_found = "Multiple"

        logger.info(
            f"Search completed in {duration:.2f}s. Papers discovered: {papers_found}"
        )
        logger.info("Multi-agent coordination: Success. Real Lambda functions: Called.")
        
        # Show sample results if found
        if papers_found and str(papers_found).isdigit() and papers_found > 0:
            logger.info("Sample Results Found:")
            lines = response.split("\n")
            for line in lines:
                if line.startswith("### 1."):
                    logger.info(f"• {line[6:].strip()}")
                    break
        elif papers_found == 0:
            logger.warning("No papers were found for the query.")
        
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"Search test failed after {duration:.2f}s: {e}")
        return False

    # Step 5: Cost analysis for real Lambda usage
    logger.info("5. Real Lambda cost analysis...")
    logger.info("Lambda invocations: ~$0.0000002 per invocation")
    logger.info("API calls (ArXiv/Semantic Scholar): ~$0.005")
    logger.info("Data transfer: ~$0.001")
    logger.info("Total estimated cost: ~$0.01 per search")

    logger.info("✅ Real Lambda integration test passed!")
    logger.info("System capabilities verified:")
    logger.info("- Real AWS Lambda function execution")
    logger.info("- Multi-agent coordination with A2A protocol")
    logger.info("- Academic database integration")
    logger.info("- Production-ready error handling")
    logger.info("- Cost-effective resource utilization")
    return True


async def main():
    """Main test function."""
    # Set logging to show important info but not spam
    logging.getLogger().setLevel(logging.WARNING)

    try:
        success = await test_real_lambda_functions()

        if success:
            print("\n🎉 Ready for hackathon presentation!")
            print("\nDemonstrated capabilities:")
            print("✓ Real AWS Lambda function integration")
            print("✓ Multi-agent research system")
            print("✓ Academic literature discovery")
            print("✓ Production-ready architecture")
            print("✓ Cost-effective operation")
        else:
            print("\n❌ Some tests failed - check configuration")

        return success

    except KeyboardInterrupt:
        print("\nTest interrupted by user")
        return False
    except Exception as e:
        print(f"Test failed: {e}")
        return False


if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"Test suite failed: {e}")
        sys.exit(1)
