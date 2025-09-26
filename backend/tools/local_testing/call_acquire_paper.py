import sys
import os
import json

# --- MOCK ENVIRONMENT VARIABLES ---
os.environ["RAW_BUCKET_NAME"] = "mock-raw-bucket"
os.environ["HTTP_TIMEOUT_SECONDS"] = "5"  # shorter for testing

# Now import after env vars are set
sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
from tools.acquire_paper.app import lambda_handler


class DummyContext:
    def __init__(self):
        self.aws_request_id = "test-request-id"
        self.function_name = "test-function"
        self.memory_limit_in_mb = 128
        self.invoked_function_arn = (
            "arn:aws:lambda:us-east-1:123456789012:function:test-function"
        )
        self.log_group_name = "/aws/lambda/test-function"
        self.log_stream_name = "2025/09/16/[$LATEST]abcdef1234567890"

    def get_remaining_time_in_millis(self):
        return 300000


def run_test_event(query_value):
    event = {"body": json.dumps({"pdf_url": query_value})}
    context = DummyContext()

    print(f"=== Testing with query: {query_value} ===")
    result = lambda_handler(event, context)
    print("Status Code:", result.get("statusCode"))
    print("Body:", result.get("body"))
    print()


if __name__ == "__main__":
    run_test_event(
        "https://www.semanticscholar.org/paper/An-Image-is-Worth-16x16-Words%3A-Transformers-for-at-Dosovitskiy-Beyer/268d347e8a55b5eb82fb5e7d2f800e33c75ab18a"
    )
