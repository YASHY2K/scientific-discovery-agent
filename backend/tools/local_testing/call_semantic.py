import sys
import os
import json

sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
from tools.search_semantic_scholar.app import lambda_handler


class DummyContext:
    # Simulate AWS Lambda context object with just minimal props
    def __init__(self):
        self.aws_request_id = "test-request-id"
        self.function_name = "test-function"
        self.memory_limit_in_mb = 128
        self.invoked_function_arn = (
            "arn:aws:lambda:us-east-1:123456789012:function:test-function"
        )
        self.log_group_name = "/aws/lambda/test-function"
        self.log_stream_name = "2025/09/16/[$LATEST]abcdef1234567890"
        # timestamp etc. could be added if needed

    def get_remaining_time_in_millis(self):
        return 300000  # just a stub value


def run_test_event(query_value):
    # Construct a mock event similar to API Gateway proxy event style
    event = {
        "body": json.dumps({"query": query_value}),
        # if needed, you can simulate other API Gateway fields, headers, etc.
    }
    context = DummyContext()

    print(f"=== Testing with query: {query_value} ===")
    result = lambda_handler(event, context)
    print("Status Code:", result.get("statusCode"))
    print("Body:", result.get("body"))
    print()


if __name__ == "__main__":
    # Test with no query provided
    # run_test_event(None)

    # # Test with an empty query string
    # run_test_event("")

    # Test with a normal query
    run_test_event("transformers")

    # Possibly test with a special string that might trigger errors, e.g. very long string
    # run_test_event("a" * 5000)
