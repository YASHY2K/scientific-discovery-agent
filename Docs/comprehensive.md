# Comprehensive System Architecture Explanation for the Autonomous Research Agent

> **Last Updated:** January 21, 2025  
> **Implementation Status:** Reflects actual production deployment  
> **Document Version:** 2.0

Let me walk you through this architecture as if we're planning to build it together, explaining every service choice and how each piece contributes to the whole system. Think of this as building a sophisticated research team, but instead of humans, we're using AI agents that can work autonomously while giving us complete visibility into their thought process.

## Part 1: Executive Summary and Core Framework Choice

The goal of this project is to create a fully autonomous system that can conduct academic research without human intervention. When a user asks something like "Research the latest advances in Tree of Thoughts prompting," the system should independently find relevant papers, analyze them, critique its own work, and produce a comprehensive research report.

We're choosing **AWS Strands Agents SDK** as our core framework because it recently reached version 1.0 in July 2025, making it production-ready for production deployment. The beauty of Strands is that it takes a model-driven approach, meaning we can build sophisticated AI agents with minimal code while maintaining full control over their behavior. It also natively supports something called the Agent-to-Agent (A2A) protocol, which is crucial for our multi-agent design.

The technology stack centers on four core pillars:

- **AWS Strands Agents SDK** (v1.0+) for agent orchestration and development
- **AWS Bedrock AgentCore Runtime** for production agent hosting and execution
- **AWS Bedrock AgentCore Gateway** for secure MCP-based tool access
- **Claude Sonnet 4** (us.anthropic.claude-sonnet-4-20250514-v1:0) as the reasoning engine for all our agents

### Production Deployment Platform

A critical architectural decision is using **AWS Bedrock AgentCore Runtime** as the production deployment platform for all agents. Unlike traditional Lambda-based agent deployments, AgentCore Runtime provides:

- **Managed agent hosting**: All Strands agents run within the AgentCore Runtime environment, eliminating the need to manage individual Lambda functions for each agent
- **Built-in state management**: Native support for agent state persistence across invocations using ToolContext
- **Streamlined deployment**: Deploy agents using the `BedrockAgentCoreApp` pattern with a single entrypoint
- **Integrated observability**: Built-in logging and monitoring for agent execution

This approach separates concerns cleanly: agents (non-deterministic reasoning) run in AgentCore Runtime, while tools (deterministic operations) run as Lambda functions accessed through the AgentCore Gateway.

## Part 2: Multi-Agent Architecture Design

Let me explain the agent hierarchy and how they work together. This is where the architecture gets interesting.

### The Primary Orchestrator Agent

Think of the orchestrator as the research team leader. This agent receives the initial research request and understands the big picture. It doesn't do the detailed work itself but knows which specialist to engage and when. The orchestrator is powered by Claude 3.5 Sonnet and has the intelligence to:

- Break down complex requests
- Manage workflows
- Handle quality control feedback
- Adaptively re-plan when needed

What makes this special in Strands is that the orchestrator sees the specialist agents as "tools" it can use. Through the A2A protocol, when the orchestrator decides it needs planning help, it can invoke the Planner Agent just like calling a function, but that "function" is actually another intelligent agent that can reason and make decisions.

### The Specialist Agents

We have five specialist agents, each with their own Claude 3.5 Sonnet brain and specific expertise:

#### 1. Research Planner Agent

Specializes in strategy. When given a research topic, it:

- Breaks it down into actionable steps
- Identifies key search terms
- Suggests research angles
- Creates a structured plan
- Outputs research objectives, key search queries, expected paper counts, and success criteria

#### 2. Paper Searcher Agent

The literature discovery specialist. It:

- Executes searches across academic databases
- Refines queries based on results
- Filters papers by relevance and recency
- Identifies both seminal works and recent breakthroughs
- Adds intelligence on top of deterministic search tools
- Understands when searches aren't yielding good results and adjusts approach

#### 3. Paper Analyzer Agent

Performs deep technical analysis. It:

- Extracts key methodologies from papers
- Identifies novel contributions
- Compares approaches across multiple papers
- Synthesizes findings
- Uses deterministic tools to extract text from PDFs but applies reasoning to understand what's important

#### 4. Research Critique Agent

Serves as quality control. It:

- Evaluates whether the research is comprehensive
- Identifies gaps in analysis
- Verifies technical accuracy
- Provides specific feedback
- Can reject work and request revisions, creating a quality feedback loop

#### 5. Report Generator Agent

The technical writer. It:

- Takes all analyzed findings
- Compiles them into well-structured reports
- Creates proper sections, executive summaries, citations
- Adds visualizations where appropriate

### The Critical Agent-Tool Distinction

Here's a crucial architectural principle: **agents and tools are fundamentally different**.

- **Agents** are non-deterministic - they think, reason, and make decisions
- **Tools** are deterministic - given the same input, they always produce the same output

For example, when the Searcher Agent needs to find papers on arXiv, it calls the `arxiv_search_tool`. That tool always returns the same papers for the same search query. The intelligence comes from the Searcher Agent deciding what queries to try, how to refine them, and which papers are actually relevant.

The magic of Strands is that specialist agents are exposed as "tools" to the orchestrator through the A2A protocol. So from the orchestrator's perspective, it can "use" the Planner Agent like a tool, but that tool is actually another reasoning entity that can make intelligent decisions.

### Implementation: Agent-as-Tool Pattern

In practice, this is implemented using Strands' `@tool` decorator with `ToolContext` for state management. Here's how the orchestrator exposes specialist agents as tools:

```python
from strands import Agent, tool, ToolContext
from strands.models import BedrockModel

# Each specialist agent is wrapped as a tool
@tool(context=True)
def planner_tool(query: str, tool_context: ToolContext) -> str:
    """Execute the planning phase"""
    # Store state for workflow tracking
    tool_context.agent.state.set("user_query", query)
    tool_context.agent.state.set("phase", "PLANNING")

    # Call the specialist agent's execution function
    response = execute_planning(query)

    # Store results in shared state
    tool_context.agent.state.set("research_plan", response)
    tool_context.agent.state.set("current_subtopic_index", 0)

    return response

@tool(context=True)
def searcher_tool(query: str, tool_context: ToolContext) -> str:
    """Execute the search phase"""
    tool_context.agent.state.set("phase", "SEARCH")

    # Get current subtopic index from state
    current_index = tool_context.agent.state.get("current_subtopic_index") or 0

    # Execute search and track processed papers
    response = execute_search(query)

    # Store results by subtopic
    all_papers = tool_context.agent.state.get("all_papers_by_subtopic") or {}
    all_papers[str(current_index)] = response
    tool_context.agent.state.set("all_papers_by_subtopic", all_papers)

    return response
```

The `ToolContext` provides access to the agent's state, enabling:

- **Workflow tracking**: Store current phase, iteration counts, revision history
- **Data sharing**: Pass results between specialist agents
- **State persistence**: Maintain context across multiple tool invocations

### Orchestrator System Prompt

The orchestrator agent is guided by a comprehensive system prompt that defines the workflow phases:

```python
ORCHESTRATOR_PROMPT = """You are the Chief Research Orchestrator managing a team of specialist AI agents.

Your role is to coordinate a comprehensive research workflow through multiple phases:

## Agent Team
1. **Planner Agent**: Decomposes complex queries into research sub-topics
2. **Searcher Agent**: Finds relevant academic papers from arXiv and Semantic Scholar
3. **Analyzer Agent**: Performs deep analysis of papers based on search guidance
4. **Critique Agent**: Validates research quality and identifies gaps
5. **Reporter Agent**: Tools for writing the report section by section

## Workflow Phases

### Phase 1: PLANNING
- Receive user research query
- Call `planner_tool` with the query
- Store research plan in state

### Phase 2: SEARCH
- Call `searcher_tool` with sub-topic queries
- Wait for completion of paper searches
- Store paper metadata

### Phase 3: ANALYSIS
- Call `analyzer_tool` for each paper using S3 paths
- Store analysis results by subtopic

### Phase 4: QUALITY ASSURANCE
- Call `critique_tool` with complete research
- If REVISE: execute required revisions based on feedback
- If APPROVED: proceed to reporting

### Phase 5: REPORTING
- Call `write_report_section_tool` for each section
- Call `finalize_report_tool` to assemble final report

## State Management
The orchestrator maintains these state variables:
- `user_query`: Original research question
- `research_plan`: Full plan from planner
- `analyses`: Dictionary mapping sub-topic IDs to analysis results
- `revision_count`: Number of revision cycles executed
- `phase`: Current workflow phase
"""
```

This prompt-driven approach ensures the orchestrator follows a consistent workflow while maintaining flexibility to handle revisions and edge cases.

## Part 3: AWS Services Architecture

Now let's detail every AWS service we actually use and exactly what it does in the implemented system.

### AWS Bedrock AgentCore Runtime and Gateway

The foundation of our architecture is the AgentCore platform, which provides managed infrastructure for agent hosting and tool access.

#### AgentCore Runtime

**Purpose**: Hosts and executes all Strands agents in a managed production environment.

**Key Features**:

- Runs all six agents (orchestrator + five specialists) in a single managed runtime
- Handles agent lifecycle, invocation, and state management
- Provides built-in observability and logging
- Eliminates need for individual Lambda functions per agent

**Deployment Pattern**:

```python
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from strands import Agent
from strands.models import BedrockModel

# Initialize the AgentCore application
app = BedrockAgentCoreApp()

# Define the entrypoint for agent invocation
@app.entrypoint
def invoke(payload):
    user_query = payload.get("user_query", "No query provided.")

    # Create orchestrator agent with all specialist tools
    orchestrator_agent = Agent(
        model=model,
        system_prompt=ORCHESTRATOR_PROMPT,
        tools=[
            planner_tool,
            searcher_tool,
            analyzer_tool,
            critique_tool,
            write_report_section_tool,
            finalize_report_tool,
        ]
    )

    # Execute the agent
    response = orchestrator_agent(user_query)
    return response

# Run the application
if __name__ == "__main__":
    app.run()
```

This single deployment hosts all agent logic, with the runtime managing execution, scaling, and resource allocation.

#### AgentCore Gateway

**Purpose**: Provides secure MCP (Model Context Protocol) endpoints for agents to access Lambda-based tools.

**Key Features**:

- Exposes Lambda functions as MCP tools
- Handles authentication via Cognito OAuth
- Manages tool discovery and invocation
- Provides secure, auditable tool access

**Setup Process** (using `bedrock_agentcore_starter_toolkit`):

```python
from bedrock_agentcore_starter_toolkit.operations.gateway.client import GatewayClient

# Initialize gateway client
client = GatewayClient(region_name="us-east-1")

# Create Cognito authorizer for OAuth authentication
cognito_response = client.create_oauth_authorizer_with_cognito("ResearchAgentGW")

# Create the MCP gateway with Cognito integration
gateway = client.create_mcp_gateway(
    authorizer_config=cognito_response["authorizer_config"]
)

# Add Lambda functions as gateway targets
lambda_target = client.create_mcp_gateway_target(
    gateway=gateway,
    target_type="lambda"
)
```

**Tool Registration**: Each Lambda tool must grant invoke permissions to the gateway's IAM role:

```json
{
  "Effect": "Allow",
  "Principal": {
    "Service": "bedrock.amazonaws.com"
  },
  "Action": "lambda:InvokeFunction",
  "Resource": "<LambdaToolArn>"
}
```

**Agent Integration**: Agents connect to the gateway using MCP clients:

```python
from strands.tools.mcp import MCPClient
from mcp.client.streamable_http import streamablehttp_client

# Initialize MCP client with gateway URL and auth token
mcp_client = MCPClient(
    lambda: streamablehttp_client(
        gateway_url,
        headers={"Authorization": f"Bearer {gateway_auth_token}"}
    )
)

# Start connection and list available tools
mcp_client.start()
tools = mcp_client.list_tools_sync()

# Create agent with MCP tools
agent = Agent(model=model, system_prompt=prompt, tools=tools)
```

### Lambda Functions (Tools Only)

**Important**: In this architecture, Lambda functions serve exclusively as deterministic tools, not as agent hosts. All agent logic runs in AgentCore Runtime.

We have five primary Lambda tool functions:

#### Tool 1: ArXiv Search (`Arxiv___search_arxiv`)

- **Purpose:** Searches arXiv preprint repository for academic papers
- **Input:** `{"body": {"query": "search terms", "limit": 5}}`
- **Output:** List of papers with metadata (title, authors, abstract, PDF URL)
- **Accessed by:** Searcher Agent via AgentCore Gateway

#### Tool 2: Semantic Scholar Search (`SemanticScholar___search_semantic_scholar`)

- **Purpose:** Searches Semantic Scholar for peer-reviewed papers
- **Input:** `{"body": {"query": "search terms", "action": "search_paper"}}`
- **Output:** List of papers with citation data and metadata
- **Accessed by:** Searcher Agent via AgentCore Gateway

#### Tool 3: Paper Processing (`PaperProcessing___paper_processing`)

- **Purpose:** Downloads PDFs, extracts text, chunks content, and stores in S3
- **Input:** `{"body": {"pdf_url": "URL to paper PDF"}}`
- **Output:** S3 path to processed chunks (e.g., `s3://bucket/paper-id/chunks.json`)
- **Caching:** Checks S3 before reprocessing to avoid duplicate work
- **Accessed by:** Searcher Agent via AgentCore Gateway

#### Tool 4: S3 Document Download (`download_s3_document`)

- **Purpose:** Retrieves processed paper content from S3 for analysis
- **Input:** `{"s3_chunks_path": "s3://bucket/prefix/chunks.json"}`
- **Output:** Full text content of the document
- **IAM Requirements:** Requires S3 read permissions via assumed role
- **Accessed by:** Analyzer Agent (direct tool, not via gateway)

#### Tool 5: Preprocess Text

- **Purpose:** Cleans and normalizes extracted text for analysis
- **Input:** Raw text from PDF extraction
- **Output:** Cleaned, structured text ready for LLM analysis
- **Accessed by:** Paper processing pipeline

### Storage Services

#### Amazon S3

**Primary Bucket**: `ai-agent-hackathon-processed-pdf-files`

**Purpose**: Stores processed paper content for analysis

**Structure**:

```
s3://ai-agent-hackathon-processed-pdf-files/
  ├── {paper-id}/
  │   ├── chunks.json          # Chunked paper content
  │   ├── metadata.json         # Paper metadata
  │   └── raw.txt              # Raw extracted text
```

**Usage Pattern**:

- Paper Processing tool writes extracted and chunked content
- Analyzer Agent reads chunks for analysis
- Implements caching: checks for existing content before reprocessing
- Reduces redundant PDF downloads and text extraction

**Access Control**:

- Analyzer Agent assumes IAM role for S3 read access
- Role ARN stored in SSM Parameter Store: `/scientific-agent/config/s3-access-role-arn`
- Cross-account access supported via role assumption

**Implementation Example** (from Analyzer Agent):

```python
import boto3
from botocore.exceptions import ClientError

# Assume role for S3 access
sts_client = boto3.client('sts')
assumed_role = sts_client.assume_role(
    RoleArn=role_arn,
    RoleSessionName='AnalyzerAgentSession'
)

# Create S3 client with assumed credentials
s3_client = boto3.client(
    's3',
    aws_access_key_id=assumed_role['Credentials']['AccessKeyId'],
    aws_secret_access_key=assumed_role['Credentials']['SecretAccessKey'],
    aws_session_token=assumed_role['Credentials']['SessionToken']
)

# Download document
response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
content = response['Body'].read().decode('utf-8')
```

#### Amazon DynamoDB

**Status**: Not currently used in the implemented system.

**Future Considerations**: Could be added for:

- Session state persistence across long-running research tasks
- User query history and report metadata
- Rate limiting and usage tracking

### Frontend and API Layer

#### Streamlit Frontend

**Purpose**: Provides the user interface for submitting research queries and viewing results

**Implementation**: Python-based Streamlit application (`frontend/app.py`)

**Key Features**:

- Simple text input for research queries
- Direct invocation of AgentCore Runtime
- Real-time display of agent responses
- Report viewing and download

**Deployment**: Can be deployed on various platforms (EC2, ECS, local development)

#### API Gateway

**Status**: Not currently used for agent invocation in the implemented system.

**Current Approach**: Frontend directly invokes AgentCore Runtime entrypoint

**Future Considerations**: Could add API Gateway for:

- Rate limiting and throttling
- Request/response transformation
- Multi-tenant access control
- Usage analytics

#### Real-Time Communication

**Status**: SNS and WebSocket APIs are not implemented in the current system.

**Current Observability**: Relies on Strands built-in logging and AgentCore Runtime observability features

**Future Work**: Could implement real-time agent thought streaming using:

- WebSocket API for bidirectional communication
- SNS for event fan-out
- DynamoDB for connection state management

### AI/ML Services

#### Amazon Bedrock

**Models Used**:

- **Claude Sonnet 4** (`us.anthropic.claude-sonnet-4-20250514-v1:0`): Powers the orchestrator agent
- **Claude 3.5 Sonnet** (`us.anthropic.claude-3-5-sonnet-20240620-v1:0`): Powers specialist agents (Planner, Searcher, Analyzer, Critique, Reporter)
- **Claude 3.5 Haiku** (`us.anthropic.claude-3-5-haiku-20241022-v1:0`): Used by Searcher Agent for efficient search operations

**Access Pattern**:

```python
from strands.models import BedrockModel

# Configure model for agent
model = BedrockModel(
    model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
    temperature=0.3
)

# Create agent with model
agent = Agent(model=model, system_prompt=prompt, tools=tools)
```

**Features Used**:

- Streaming responses for real-time feedback
- Structured output for JSON responses
- Tool use for agent-to-agent communication

### Supporting Services

#### AWS Systems Manager (SSM) Parameter Store

**Purpose**: Stores configuration parameters for secure access

**Parameters Stored**:

- `/scientific-agent/config/agentcore-gateway-url`: Gateway endpoint URL
- `/scientific-agent/config/cognito-discovery-url`: Cognito OAuth discovery endpoint
- `/scientific-agent/config/access-token`: OAuth access token (refreshed automatically)
- `/scientific-agent/config/ac-user-id`: Cognito client ID
- `/scientific-agent/config/ac-user-secret`: Cognito client secret
- `/scientific-agent/config/ac-user-scope`: OAuth scopes
- `/scientific-agent/config/s3-access-role-arn`: IAM role for S3 access

**Usage Pattern**:

```python
import boto3

ssm_client = boto3.client('ssm')
response = ssm_client.get_parameters(
    Names=['/scientific-agent/config/agentcore-gateway-url'],
    WithDecryption=True
)
gateway_url = response['Parameters'][0]['Value']
```

#### Amazon Cognito

**Purpose**: Provides OAuth authentication for AgentCore Gateway access

**Configuration**:

- User Pool created automatically by `bedrock_agentcore_starter_toolkit`
- OAuth 2.0 client credentials flow
- JWT tokens for gateway authentication

**Token Refresh Logic**:

```python
def get_token(client_id, client_secret, scope_string, url):
    """Get OAuth access token from Cognito"""
    response = requests.post(
        url,
        data={
            'grant_type': 'client_credentials',
            'client_id': client_id,
            'client_secret': client_secret,
            'scope': scope_string
        },
        headers={'Content-Type': 'application/x-www-form-urlencoded'}
    )
    return response.json()
```

**Automatic Token Refresh**: When MCP client receives 401 Unauthorized, it automatically refreshes the token and retries

#### AWS IAM

**Key Roles**:

- **AgentCore Runtime Role**: Allows agents to invoke Bedrock models
- **Gateway Role**: Allows gateway to invoke Lambda tools
- **Lambda Tool Roles**: Allow tools to access S3, SSM, and other AWS services
- **S3 Access Role**: Assumed by Analyzer Agent for cross-account S3 access

**Permission Boundaries**:

- Least privilege principle applied
- Specific resource ARNs in policies
- Time-limited role assumptions

#### Amazon CloudWatch

**Logging**:

- AgentCore Runtime logs agent execution
- Lambda function logs for each tool
- Structured logging with log levels (DEBUG, INFO, ERROR)

**Monitoring**:

- Lambda invocation metrics
- Bedrock API call metrics
- S3 access patterns
- Error rates and latencies

**Example Log Output**:

```
INFO | strands | Initializing Searcher Agent...
DEBUG | strands | Connecting MCP Client (Attempt 1/2)...
INFO | strands | MCP Client connected successfully
INFO | strands | Loaded 3 tools: Arxiv___search_arxiv, SemanticScholar___search_semantic_scholar, PaperProcessing___paper_processing
```

## Part 4: Workflow Execution Details

Let me walk you through exactly what happens when a user submits a research request, step by step, based on the actual implementation.

### Step 1: Request Initiation

The user types "Research Tree of Thoughts papers" in the Streamlit interface and clicks submit. The frontend invokes the AgentCore Runtime entrypoint with the payload:

```python
payload = {
    "user_query": "Research Tree of Thoughts papers"
}
```

### Step 2: AgentCore Runtime Initialization

The AgentCore Runtime receives the request and executes the entrypoint function:

```python
@app.entrypoint
def invoke(payload):
    user_query = payload.get("user_query", "No query provided.")

    # Create orchestrator agent with all tools
    orchestrator_agent = Agent(
        model=model,
        system_prompt=ORCHESTRATOR_PROMPT,
        tools=[planner_tool, searcher_tool, analyzer_tool,
               critique_tool, write_report_section_tool, finalize_report_tool]
    )

    # Execute the agent
    response = orchestrator_agent(user_query)
    return response
```

The orchestrator agent is initialized with access to all specialist agent tools and begins reasoning.

### Step 3: Planning Phase

The orchestrator analyzes the query and decides to call `planner_tool`:

```python
@tool(context=True)
def planner_tool(query: str, tool_context: ToolContext) -> str:
    # Store query in state
    tool_context.agent.state.set("user_query", query)
    tool_context.agent.state.set("phase", "PLANNING")

    # Execute planning
    response = execute_planning(query)

    # Store plan in state
    tool_context.agent.state.set("research_plan", response)
    tool_context.agent.state.set("current_subtopic_index", 0)

    return response
```

The Planner Agent creates a structured research plan with sub-topics:

```json
{
  "research_approach": "comprehensive_survey",
  "sub_topics": [
    {
      "id": "ST1",
      "description": "Foundational Tree of Thoughts papers",
      "priority": 1,
      "suggested_keywords": ["tree of thoughts", "ToT prompting"],
      "search_guidance": {
        "focus_on": "Original methodology and core algorithms",
        "must_include": "Performance benchmarks and comparisons",
        "avoid": "Unrelated prompting techniques"
      }
    }
  ]
}
```

### Step 4: Literature Discovery

The orchestrator calls `searcher_tool` with the sub-topic query. The Searcher Agent:

1. **Initializes MCP connection** to AgentCore Gateway
2. **Calls ArXiv search tool** via gateway:
   ```python
   Arxiv___search_arxiv({"body": {"query": "tree of thoughts prompting", "limit": 5}})
   ```
3. **Calls Semantic Scholar tool** via gateway:
   ```python
   SemanticScholar___search_semantic_scholar({"body": {"query": "ToT reasoning LLM", "action": "search_paper"}})
   ```
4. **Selects top papers** based on relevance
5. **Initiates paper processing** for each selected paper:
   ```python
   PaperProcessing___paper_processing({"body": {"pdf_url": "https://arxiv.org/pdf/2305.10601.pdf"}})
   ```

The tool returns S3 paths for processed papers:

```python
{
  "selected_papers": [
    {
      "id": "arxiv:2305.10601",
      "title": "Tree of Thoughts: Deliberate Problem Solving with Large Language Models",
      "s3_chunks_path": "s3://ai-agent-hackathon-processed-pdf-files/2305.10601v1/chunks.json",
      "processing_initiated": true
    }
  ]
}
```

**State Management**: The orchestrator stores papers by subtopic:

```python
tool_context.agent.state.set("all_papers_by_subtopic", {
    "0": [paper1, paper2, paper3]
})
```

### Step 5: Deep Analysis

The orchestrator calls `analyzer_tool` with the S3 paths:

```python
@tool(context=True)
def analyzer_tool(paper_uris: List[str], tool_context: ToolContext) -> str:
    tool_context.agent.state.set("phase", "ANALYSIS")

    # Get current subtopic index
    current_index = tool_context.agent.state.get("current_subtopic_index") or 0

    # Execute analysis
    response = execute_analysis(paper_uris)

    # Store analysis by subtopic
    analyses = tool_context.agent.state.get("analyses") or {}
    analyses[str(current_index)] = response
    tool_context.agent.state.set("analyses", analyses)

    return response
```

The Analyzer Agent:

1. **Downloads paper content** from S3 using `download_s3_document` tool
2. **Analyzes each paper** using Claude Sonnet 3.5
3. **Extracts structured insights**:

```json
{
  "papers_analyzed": [
    {
      "s3_chunks_path": "s3://bucket/2305.10601v1/chunks.json",
      "title": "Tree of Thoughts: Deliberate Problem Solving with Large Language Models",
      "key_findings": [
        "ToT enables LLMs to explore multiple reasoning paths",
        "Achieves 74% success rate on Game of 24 vs 4% with standard prompting"
      ],
      "methodology": "Proposes tree search algorithm with LLM as both generator and evaluator",
      "contributions": [
        "Novel framework for deliberate problem solving",
        "Demonstrates significant improvements on creative tasks"
      ],
      "key_quotes": [
        "ToT allows LMs to perform deliberate decision making by considering multiple different reasoning paths"
      ]
    }
  ]
}
```

### Step 6: Quality Control Loop

The orchestrator calls `critique_tool` with all analyses:

```python
@tool(context=True)
def critique_tool(analysis_report: str, tool_context: ToolContext) -> str:
    tool_context.agent.state.set("phase", "CRITIQUE")

    # Get state for comprehensive critique
    user_query = tool_context.agent.state.get("user_query")
    research_plan = tool_context.agent.state.get("research_plan")
    analyses = tool_context.agent.state.get("analyses")
    revision_count = tool_context.agent.state.get("revision_count") or 0

    # Execute critique
    response = critique(user_query, research_plan, analyses, revision_count)

    # Store results
    critique_data = json.loads(response)
    tool_context.agent.state.set("critique_results", critique_data)

    if critique_data["verdict"] == "REVISE":
        tool_context.agent.state.set("revision_count", revision_count + 1)

    return response
```

The Critique Agent evaluates and returns:

```json
{
  "verdict": "REVISE",
  "overall_quality_score": 0.68,
  "critical_issues": [
    {
      "severity": "high",
      "issue": "Missing recent applications in code generation",
      "required_action": "Search for ToT applications in code synthesis"
    }
  ],
  "required_revisions": [
    {
      "action": "search_more_papers",
      "target": "ST1",
      "specific_query": "tree of thoughts code generation synthesis"
    }
  ]
}
```

### Step 7: Iterative Improvement

Based on the critique verdict, the orchestrator:

1. **Checks revision count** (max 1 revision allowed)
2. **Executes required revisions**:
   - Re-calls `searcher_tool` with refined query
   - Processes new papers
   - Re-calls `analyzer_tool` for new papers
3. **Re-runs critique** with updated analyses
4. **Proceeds to reporting** if approved or max revisions reached

### Step 8: Report Generation (Chunked Strategy)

Once approved, the orchestrator generates the report section by section using a modular approach:

```python
# Initialize section storage
tool_context.agent.state.set("generated_sections", {})

# Generate each section independently
sections = ["Executive Summary", "Introduction", "Main Findings",
            "Cross-Study Synthesis", "Research Gaps", "Conclusion"]

for section_name in sections:
    write_report_section_tool(section_name, tool_context)
```

Each section is generated by a temporary agent with section-specific instructions:

```python
@tool(context=True)
def write_report_section_tool(section_name: str, tool_context: ToolContext) -> str:
    # Get section-specific prompt
    section_system_prompt = REPORTER_PROMPTS.get(section_name)

    # Create temporary agent for this section
    section_agent = Agent(model=model, system_prompt=section_system_prompt)

    # Get data from state
    user_query = tool_context.agent.state.get("user_query")
    research_plan = tool_context.agent.state.get("research_plan")
    analyses = tool_context.agent.state.get("analyses")

    # Generate section content
    section_data_prompt = f"""
    Here is the data you must use to write your section:
    - Original Query: {user_query}
    - Research Plan: {json.dumps(research_plan, indent=2)}
    - Analyses: {json.dumps(analyses, indent=2)}

    Begin writing your assigned section.
    """

    response = section_agent(section_data_prompt)
    section_content = response.message["content"][0].text

    # Store section in state
    generated_sections = tool_context.agent.state.get("generated_sections") or {}
    generated_sections[section_name] = section_content
    tool_context.agent.state.set("generated_sections", generated_sections)

    return f"Successfully generated section: {section_name}"
```

**Benefits of Chunked Approach**:

- Reduces token usage per LLM call
- Allows section-specific prompting and tone
- Enables parallel section generation (future optimization)
- Easier to revise individual sections

### Step 9: Report Finalization

The orchestrator calls `finalize_report_tool` to assemble all sections:

```python
@tool(context=True)
def finalize_report_tool(tool_context: ToolContext) -> str:
    generated_sections = tool_context.agent.state.get("generated_sections") or {}

    section_order = ["Executive Summary", "Introduction", "Main Findings",
                     "Cross-Study Synthesis", "Research Gaps", "Conclusion"]

    final_report_parts = []
    user_query = tool_context.agent.state.get("user_query")
    final_report_parts.append(f"# Research Report: {user_query}\n")

    for section_name in section_order:
        final_report_parts.append(f"\n## {section_name}\n")
        section_content = generated_sections.get(section_name, "*(Not generated)*")
        final_report_parts.append(section_content)

    final_report = "\n".join(final_report_parts)
    tool_context.agent.state.set("final_report", final_report)
    tool_context.agent.state.set("phase", "COMPLETE")

    return final_report
```

### Step 10: Response Delivery

The AgentCore Runtime returns the final report to the Streamlit frontend, which displays it to the user. The complete workflow state is maintained in the agent's ToolContext throughout execution.

## Part 5: Observability and Transparency

The current implementation provides observability through built-in AWS and Strands features rather than a custom real-time "Glass Box" system.

### Current Observability Mechanisms

#### 1. Strands Built-in Logging

The Strands Agents SDK provides structured logging for agent execution:

```python
import logging

logging.getLogger("strands").setLevel(logging.DEBUG)
logging.basicConfig(
    format="%(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler()]
)
```

**Log Output Examples**:

```
INFO | strands | Initializing Searcher Agent...
DEBUG | strands | Connecting MCP Client (Attempt 1/2)...
INFO | strands | MCP Client connected successfully
INFO | strands | Loaded 3 tools: Arxiv___search_arxiv, SemanticScholar___search_semantic_scholar
DEBUG | strands | Tool call: Arxiv___search_arxiv with query "tree of thoughts"
INFO | strands | Tool returned 5 papers
```

#### 2. AgentCore Runtime Observability

AgentCore Runtime provides:

- **Execution logs**: Captured in CloudWatch Logs
- **Performance metrics**: Invocation duration, memory usage
- **Error tracking**: Exception traces and failure reasons
- **State inspection**: Agent state at each phase

#### 3. CloudWatch Logs and Metrics

**Log Groups**:

- AgentCore Runtime execution logs
- Lambda tool invocation logs
- MCP gateway access logs

**Custom Metrics**:

- Papers processed per query
- Analysis completion time
- Critique revision cycles
- Report generation duration

#### 4. Agent State Tracking

The ToolContext maintains workflow state throughout execution:

```python
# State variables tracked
tool_context.agent.state.get("phase")              # Current workflow phase
tool_context.agent.state.get("revision_count")     # Number of revisions
tool_context.agent.state.get("analyses")           # Completed analyses
tool_context.agent.state.get("critique_results")   # Quality assessment
```

This enables post-execution analysis and debugging.

### Future Work: Real-Time Transparency System

A comprehensive "Glass Box" system could be implemented using:

**Architecture**:

1. **Event Generation**: Agents emit structured events at key decision points
2. **Event Publishing**: Events published to SNS topic or EventBridge
3. **Event Relay**: Lambda function relays events to WebSocket API
4. **Frontend Display**: Real-time visualization of agent reasoning

**Benefits**:

- Live visibility into agent decision-making
- User confidence through transparency
- Debugging and optimization insights
- Interactive feedback during execution

**Implementation Considerations**:

- Additional infrastructure (SNS, WebSocket API, DynamoDB for connections)
- Increased complexity and cost
- Potential latency impact on agent execution
- Privacy and security for sensitive research queries

**Current Status**: Not implemented. The system relies on post-execution log analysis and final report delivery.

## Part 6: Production Infrastructure Considerations

### Scalability

#### AgentCore Runtime Scaling

**Characteristics**:

- Managed scaling by AWS Bedrock
- Handles concurrent agent invocations
- Automatic resource allocation based on load
- No manual capacity planning required

**Limitations**:

- Subject to Bedrock service quotas
- Regional availability constraints
- Cold start latency for first invocation
- Concurrent execution limits (can be increased via quota requests)

**Scaling Strategy**:

- Monitor invocation metrics in CloudWatch
- Request quota increases for high-volume scenarios
- Consider multi-region deployment for global scale
- Implement request queuing for burst traffic

#### Lambda Tool Scaling

**Characteristics**:

- Each tool Lambda scales independently
- Concurrent execution up to account limits (default 1000)
- Sub-second scaling for traffic spikes

**Bottlenecks**:

- Paper processing tool: PDF download and extraction time
- S3 access: Throughput limits on bucket operations
- External APIs: ArXiv and Semantic Scholar rate limits

### Reliability

#### State Management

**Current Approach**: In-memory state via ToolContext

- State persists for duration of agent execution
- Lost if AgentCore Runtime restarts
- Suitable for short-to-medium research tasks (< 15 minutes)

**Failure Recovery**:

- Retry logic in MCP client (automatic token refresh)
- S3 caching prevents reprocessing on retry
- Idempotent tool operations

**Future Enhancements**:

- DynamoDB for persistent state across long-running tasks
- Checkpoint/resume capability for multi-hour research
- Dead letter queues for failed tool invocations

#### Data Durability

- **S3**: 99.999999999% durability for processed papers
- **CloudWatch Logs**: 2-week retention for debugging
- **SSM Parameters**: Encrypted configuration storage

### Cost Optimization

#### Cost Model

**Primary Cost Drivers**:

1. **Bedrock API Calls**: Largest cost component

   - Claude Sonnet 4: ~$3 per 1M input tokens, ~$15 per 1M output tokens
   - Claude 3.5 Sonnet: ~$3 per 1M input tokens, ~$15 per 1M output tokens
   - Multiple agent invocations per research query

2. **AgentCore Runtime**: Execution time and invocations

   - Charged per invocation and compute time
   - Varies by research complexity

3. **Lambda Tools**: Minimal compared to Bedrock

   - Pay per invocation and duration
   - Paper processing most expensive (PDF download/extraction)

4. **S3 Storage**: Negligible
   - Storage costs for processed papers
   - Mitigated by lifecycle policies (if implemented)

**Optimization Strategies**:

- **PDF Caching**: Check S3 before reprocessing (already implemented)
- **Efficient Prompting**: Minimize token usage in system prompts
- **Chunked Reporting**: Generate sections independently to reduce context size
- **Model Selection**: Use Haiku for simple tasks, Sonnet for complex reasoning
- **Batch Processing**: Process multiple papers in single analyzer call

**Example Cost Calculation** (per research query):

```
Orchestrator: 50K tokens input, 5K output = $0.23
Planner: 5K input, 2K output = $0.05
Searcher: 10K input, 3K output = $0.08
Analyzer (3 papers): 150K input, 10K output = $0.60
Critique: 30K input, 5K output = $0.17
Reporter (6 sections): 180K input, 15K output = $0.77
Total: ~$1.90 per research query
```

### Security

#### Authentication and Authorization

**AgentCore Gateway**:

- Cognito OAuth 2.0 client credentials flow
- JWT tokens with expiration
- Automatic token refresh on 401 errors
- Scoped access per client

**Implementation**:

```python
# Token refresh logic
if _is_unauthorized_error(e):
    token_response = get_token(
        client_id=app_config["AC_USER_ID"],
        client_secret=app_config["AC_USER_SECRET"],
        scope_string=app_config["AC_USER_SCOPE"],
        url=cognito_url
    )
    gateway_auth_token = token_response["access_token"]
    update_ssm_parameter("ACCESS_TOKEN", gateway_auth_token)
```

#### IAM Roles and Permissions

**Principle of Least Privilege**:

- AgentCore Runtime: Bedrock InvokeModel only
- Lambda Tools: Specific S3 buckets and SSM parameters
- S3 Access Role: Read-only access to processed papers bucket
- Gateway Role: Lambda InvokeFunction for registered tools only

**Cross-Account Access**:

- Analyzer Agent assumes role for S3 access
- Time-limited credentials (1 hour session)
- Audit trail via CloudTrail

#### Data Protection

**Encryption**:

- S3: Server-side encryption (SSE-S3 or SSE-KMS)
- SSM Parameters: Encrypted with KMS
- In-transit: TLS 1.2+ for all API calls

**Data Retention**:

- Processed papers: Indefinite (or lifecycle policy)
- CloudWatch Logs: 2-week retention
- Access tokens: Refreshed every hour

**Sensitive Data Handling**:

- No PII stored in logs
- Research queries may contain sensitive topics
- Consider VPC endpoints for private Bedrock access

### Monitoring and Alerting

**Key Metrics to Track**:

- AgentCore invocation success rate
- Average research completion time
- Bedrock API throttling events
- Lambda tool error rates
- S3 cache hit ratio
- Token refresh failures

**Recommended CloudWatch Alarms**:

- AgentCore invocation errors > 5% in 5 minutes
- Lambda tool failures > 10 in 5 minutes
- Bedrock throttling events > 0
- MCP client connection failures

## Communication Patterns

The implemented system uses two primary communication patterns:

### 1. Synchronous Agent Invocation

**Pattern**: Frontend → AgentCore Runtime → Response

**Characteristics**:

- Blocking call until research complete
- Suitable for short-to-medium tasks
- Simple error handling
- Direct response delivery

### 2. Agent-to-Tool Communication

**Pattern**: Agent → AgentCore Gateway → Lambda Tool → Response

**Characteristics**:

- MCP protocol over HTTPS
- OAuth authentication per request
- Synchronous tool invocation
- Automatic retry on auth failure

### 3. Agent-to-Agent Protocol (A2A)

**Pattern**: Orchestrator → Specialist Agent (via @tool decorator)

**Characteristics**:

- In-process function calls
- Shared ToolContext for state
- Non-deterministic reasoning
- Preserves agent autonomy

---

## Conclusion

This architecture creates a sophisticated, scalable research system where AI agents collaborate like a human research team. The production deployment leverages AWS Bedrock AgentCore Runtime for managed agent hosting, AgentCore Gateway for secure tool access, and a carefully designed workflow that balances quality, cost, and performance.

**Key Architectural Decisions**:

- AgentCore Runtime eliminates Lambda management overhead for agents
- MCP protocol provides secure, standardized tool access
- Chunked reporting reduces token costs and improves modularity
- S3 caching prevents redundant processing
- ToolContext enables stateful workflows without external databases

**Production Readiness**:

- ✅ Managed infrastructure (AgentCore Runtime)
- ✅ Secure authentication (Cognito OAuth)
- ✅ Cost optimization (caching, efficient prompting)
- ✅ Observability (CloudWatch, Strands logging)
- 🚧 Real-time transparency (future work)
- 🚧 Persistent state for long-running tasks (future work)

---

## Implementation Status Summary

### ✅ Fully Implemented

**Core Agent System:**

- AWS Bedrock AgentCore Runtime hosting all agents
- Orchestrator agent with Claude Sonnet 4
- Five specialist agents (Planner, Searcher, Analyzer, Critique, Reporter)
- Agent-to-agent communication via @tool decorator pattern
- ToolContext-based state management

**Tool Infrastructure:**

- AgentCore Gateway with MCP protocol
- Cognito OAuth authentication
- Five Lambda tools (search_arxiv, search_semantic_scholar, acquire_paper, extract_content, preprocess_text)
- IAM permission enforcement

**Data Management:**

- S3 caching for processed papers
- SSM Parameter Store for configuration
- CloudWatch logging and monitoring

**Frontend:**

- Streamlit web interface
- Real-time phase tracking
- Report display and download

### 🚧 Future Enhancements

**Real-Time Transparency:**

- WebSocket API for live agent thought streaming
- SNS event publishing for agent decisions
- DynamoDB connection state management
- Interactive frontend visualization

**Advanced State Management:**

- DynamoDB persistent state storage
- Checkpoint/resume for long-running tasks
- Multi-hour research session support
- State recovery after failures

**Scalability Improvements:**

- Multi-region deployment
- Request queuing system
- Provisioned concurrency for Lambda tools
- Redis caching layer

**Cost Optimization:**

- Automated cost tracking dashboard
- Model selection optimization (Haiku for simple tasks)
- Batch processing for multiple queries
- Lifecycle policies for S3 storage

**User Experience:**

- Interactive mid-execution feedback
- Customizable report templates
- Research history and favorites
- Collaborative research sessions

**Quality Enhancements:**

- Automated fact-checking integration
- Citation verification system
- Plagiarism detection
- Multi-language support

### ❌ Deprecated/Not Implemented

The following features were mentioned in early planning but are **not implemented** in the current system:

- **API Gateway REST API**: Frontend directly invokes AgentCore Runtime instead
- **DynamoDB Tables**: State managed in-memory via ToolContext (sufficient for current use cases)
- **SNS Topics**: No real-time event publishing (using CloudWatch logs instead)
- **WebSocket API**: No live streaming (phase tracking via Streamlit polling)
- **Step Functions**: Not needed with AgentCore Runtime orchestration
- **React Frontend**: Using Streamlit instead for rapid development
- **CloudFront Distribution**: Not deployed (Streamlit runs on single endpoint)

These features may be added in future iterations based on user requirements and scale needs.
