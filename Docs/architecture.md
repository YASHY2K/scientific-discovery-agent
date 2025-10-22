## **A Serverless Architecture for the Autonomous Research Agent on AWS**

> **Last Updated:** January 21, 2025  
> **Implementation Status:** Reflects production deployment as of January 2025  
> **Document Version:** 2.0

### **Section 1: Executive Summary & Architectural Vision**

#### **1.1. Project Mandate and Architectural Vision**

The primary mandate of this project is to develop a **highly autonomous, collaborative multi-agent AI system** capable of intelligently discovering, processing, and reasoning over a dynamically expanding corpus of scientific literature. This system will dramatically accelerate the traditionally laborious process of literature review, transforming months of manual effort into minutes of automated, rigorous research.

The architectural vision is a **fully serverless, event-driven, and transparent ("Glass Box")** system built entirely on **Amazon Web Services (AWS)**. This approach maximizes agility, inherent scalability, and cost-efficiency while fundamentally minimizing operational overhead. By extensively leveraging AWS managed services including **AWS Bedrock AgentCore Runtime** (for agent hosting), **AWS Bedrock AgentCore Gateway** (for secure tool access via MCP), **AWS Strands Agents SDK** (for agent orchestration), **AWS Lambda** (for deterministic tools), **Amazon S3** (for storage), and advanced AI capabilities (Amazon Bedrock with Claude Sonnet 4 and Claude 3.5 Sonnet), the development team can focus almost exclusively on refining the complex multi-agent reasoning, planning, and synthesis logic.

This architecture empowers a team of specialized AI agents to autonomously perform a complete, end-to-end cycle of academic paper discovery, retrieval, deep analysis, self-critique, and comprehensive report generation. The ultimate goal is to transform raw scientific information into actionable intelligence, significantly accelerating the pace of scientific innovation.

#### **1.2. Core Architectural Principles**

The design of the Autonomous Research Agent is guided by several foundational principles:

- **Multi-Agent Collaboration:** A hierarchical structure where a primary Orchestrator Agent intelligently delegates tasks to specialized agents (Planner, Searcher, Analyzer, Critique, Reporter) using the AWS Strands Agents SDK's `@tool` decorator pattern. This mirrors a human research team's collaborative dynamic.
- **Strict Agent-Tool Distinction:** Clear separation between non-deterministic, LLM-powered reasoning agents and deterministic, reliable utility functions (tools). Agents make decisions and run in AgentCore Runtime; tools execute specific tasks reliably as Lambda functions accessed via AgentCore Gateway.
- **"Glass Box" Transparency:** The system provides visibility into agent execution through the Strands framework's built-in observability features and the Streamlit interface, fostering trust in the AI's conclusions.
- **Serverless & Scalable:** The entire system leverages AWS Bedrock AgentCore Runtime for agent hosting and AWS Lambda for tool execution, ensuring scalability, high availability, and pay-per-use cost efficiency.
- **AI-Native Design:** Deep integration with Amazon Bedrock (Claude Sonnet 4 for orchestration, Claude 3.5 Sonnet for report generation) as the core intelligence layer for all agentic decision-making and content understanding.
- **Iterative & Self-Correcting:** Agents, particularly the Research Critique Agent, are designed to evaluate their own output, identify gaps or inaccuracies, and trigger iterative refinement loops to ensure high-quality, comprehensive results.
- **Robustness & Resilience:** Incorporates mechanisms for state persistence via ToolContext, error handling, retries, and S3 caching to ensure reliable operation and recoverability from transient failures.

---

### **Section 2: System Components and Data Flow**

This section breaks down the system into its logical layers and explains the end-to-end flow of a research task.

#### **2.1. Frontend Layer: The User's Gateway**

The user interacts with the system through a **Streamlit web application**, which provides a modern, interactive chat interface. The Streamlit app supports two operational modes:

1.  **Local Mode:** For development and testing, the frontend communicates with a FastAPI middleware server running locally, which then invokes the AgentCore Runtime.
2.  **Production Mode:** The frontend directly invokes the AWS Bedrock AgentCore Runtime using the boto3 SDK, passing the user query as a payload.

The Streamlit interface provides real-time visibility into the research workflow through a sidebar that displays agent execution status, showing progress through the Planning, Search, Analysis, Critique, and Reporting phases. This creates a "Glass Box" experience where users can observe the multi-agent system at work.

#### **2.2. The Agent Tier: An Autonomous Research Team Hosted in AgentCore Runtime**

The core of the system is a team of specialized AI agents, all built using the **AWS Strands Agents SDK** and hosted within **AWS Bedrock AgentCore Runtime**. The agents are deployed as a single application using the `BedrockAgentCoreApp` framework. Each agent is a distinct, non-deterministic reasoning entity powered by **Amazon Bedrock's Claude models**.

1.  **The Primary Orchestrator Agent:** This is the team leader, powered by **Claude Sonnet 4** (us.anthropic.claude-sonnet-4-20250514-v1:0). It receives the initial user query via the AgentCore Runtime entrypoint and is responsible for the overall strategy. It doesn't perform the detailed research itself but intelligently delegates tasks to its specialist agents. It decides the sequence of operations and adaptively re-plans based on feedback. The orchestrator maintains workflow state using the Strands `ToolContext` API.

2.  **The Specialist Agents:** These are five expert agents that the Orchestrator can call upon. In the Strands framework, they are exposed to the Orchestrator as callable tools using the `@tool(context=True)` decorator pattern:
    - **Planner Agent (`planner_tool`):** The strategist. It takes the user's high-level goal and creates a detailed, structured research plan, including key search terms and success criteria.
    - **Searcher Agent (`searcher_tool`):** The librarian. It executes searches by calling deterministic Lambda tools via the AgentCore Gateway to query academic databases (arXiv and Semantic Scholar). It adds intelligence by managing search results and tracking processed papers.
    - **Analyzer Agent (`analyzer_tool`):** The analyst. It performs deep technical analysis of papers found, synthesizing key methodologies, comparing findings, and identifying novel contributions. It maintains revision history for iterative improvement.
    - **Critique Agent (`critique_tool`):** The quality assurance specialist. This agent reviews the work of the other agents, checking for completeness, accuracy, and logical coherence. It provides specific feedback and can trigger a crucial **feedback loop**, forcing the other agents to revise and improve their work.
    - **Reporter Agent (`write_report_section_tool`, `finalize_report_tool`):** The technical writer, powered by **Claude 3.5 Sonnet**. Once the research is approved by the Critique Agent, this agent compiles all the validated findings into a comprehensive, well-structured final report using a modular section-by-section approach.

#### **2.3. The Tool Tier: Deterministic Lambda Functions Accessed via AgentCore Gateway**

Tools are the reliable, deterministic functions that the agents choose to use. They do not reason; they execute a specific task. Each tool is implemented as a separate, single-purpose **AWS Lambda** function for isolation and independent scaling. These Lambda functions are registered with the **AWS Bedrock AgentCore Gateway** as MCP (Model Context Protocol) targets, providing secure, authenticated access for agents.

The actual Lambda tools deployed in the system are:

- **`search_arxiv`:** Takes a query string and reliably returns a list of papers from the arXiv API.
- **`search_semantic_scholar`:** Queries the Semantic Scholar API for academic papers based on search terms.
- **`acquire_paper`:** Downloads and retrieves paper content from various sources.
- **`extract_content`:** Takes a PDF or document, extracts its text content, and caches the result in S3 to avoid redundant work.
- **`preprocess_text`:** Cleans and preprocesses extracted text for analysis.

These tools are invoked by the Searcher and Analyzer agents through the AgentCore Gateway, which handles authentication via Cognito OAuth and enforces IAM permissions for Lambda invocation.

#### **2.4. AgentCore Gateway: Secure Tool Access via MCP Protocol**

The **AWS Bedrock AgentCore Gateway** serves as the secure bridge between agents running in AgentCore Runtime and the Lambda tool functions. It implements the Model Context Protocol (MCP), providing a standardized interface for tool discovery and invocation.

**Key Features:**

- **MCP Endpoint:** Provides a single, secure endpoint where agents can discover and invoke all registered Lambda tools.
- **Cognito OAuth Authentication:** The gateway is secured with a Cognito User Pool, ensuring only authenticated agents can access tools.
- **IAM Permission Enforcement:** Each Lambda tool must grant the gateway's IAM role permission to invoke it, following the principle of least privilege.
- **Tool Registration:** Lambda functions are registered as MCP targets using the `bedrock_agentcore_starter_toolkit`, which automates the creation of the gateway, Cognito authorizer, and tool registration.

**Setup Process:**

The gateway is deployed using Python code that leverages the `bedrock_agentcore_starter_toolkit`:

```python
from bedrock_agentcore_starter_toolkit.operations.gateway.client import GatewayClient

client = GatewayClient(region_name="us-east-1")

# Create Cognito authorizer
cognito_response = client.create_oauth_authorizer_with_cognito("LambdaAuthGW")

# Create MCP Gateway
gateway = client.create_mcp_gateway(
    authorizer_config=cognito_response["authorizer_config"]
)

# Register Lambda tools as gateway targets
lambda_target = client.create_mcp_gateway_target(gateway=gateway, target_type="lambda")
```

#### **2.5. Data Layer: The System's Memory**

- **Amazon S3:** Used for object storage with two primary purposes:

  - **Paper Cache:** Stores extracted PDF text and preprocessed content to improve speed and reduce costs by avoiding redundant processing.
  - **Report Storage:** Stores the final research reports generated by the Reporter agent.

- **Agent State Management:** The AWS Strands framework provides built-in state management through the `ToolContext` API. The orchestrator maintains workflow state including:
  - `user_query`: Original research question
  - `research_plan`: Full plan from planner
  - `analyses`: Dictionary mapping sub-topics to analysis results
  - `revision_count`: Number of revision cycles executed
  - `phase`: Current workflow phase
  - `critique_results`: Latest critique feedback
  - `generated_sections`: Report sections as they're written
  - `final_report`: Complete generated report

This architecture creates a powerful, transparent, and truly autonomous system. By clearly separating the reasoning "Agents" (hosted in AgentCore Runtime) from the executing "Tools" (Lambda functions accessed via AgentCore Gateway) and using a model-driven framework like AWS Strands, the system can dynamically plan and adapt, mirroring the collaborative process of a human research team while operating at the scale and speed of the cloud.

## Implementation Status

### ✅ Implemented Features

- **AgentCore Runtime Deployment**: All agents hosted in AWS Bedrock AgentCore Runtime using BedrockAgentCoreApp
- **AgentCore Gateway with MCP**: Secure tool access via Model Context Protocol with Cognito OAuth authentication
- **Multi-Agent Orchestration**: Orchestrator coordinates five specialist agents (Planner, Searcher, Analyzer, Critique, Reporter) using @tool decorator pattern
- **Lambda Tool Integration**: Five deterministic tools (search_arxiv, search_semantic_scholar, acquire_paper, extract_content, preprocess_text) accessible via gateway
- **State Management**: Workflow state maintained using Strands ToolContext API across agent invocations
- **S3 Caching**: Paper content cached in S3 to avoid redundant processing
- **Streamlit Frontend**: Interactive chat interface with real-time phase tracking
- **CloudWatch Observability**: Comprehensive logging and monitoring for agents and tools

### 🚧 Planned Enhancements

- **Real-Time Transparency System**: WebSocket-based live streaming of agent thoughts and decisions to frontend
- **Persistent State Management**: DynamoDB integration for long-running research tasks with checkpoint/resume capability
- **Advanced Caching**: Multi-tier caching strategy with Redis for frequently accessed papers
- **Multi-Region Deployment**: Geographic distribution for improved latency and availability
- **Cost Analytics Dashboard**: Real-time cost tracking and optimization recommendations
- **Interactive Feedback Loop**: User ability to provide mid-execution guidance to agents
- **Report Templates**: Customizable report formats for different research domains
- **Batch Processing**: Queue-based system for processing multiple research queries efficiently

---

### **Section 3: Architecture Diagram and Data Flow**

The following diagram illustrates the complete system architecture and data flow from user interaction through agent execution to tool invocation:

```mermaid
graph TB
    User[User via Streamlit] -->|Research Query| Runtime[AWS Bedrock AgentCore Runtime]
    Runtime -->|Hosts| Orch[Orchestrator Agent<br/>Claude Sonnet 4]

    Orch -->|@tool calls| Planner[Planner Agent]
    Orch -->|@tool calls| Searcher[Searcher Agent]
    Orch -->|@tool calls| Analyzer[Analyzer Agent]
    Orch -->|@tool calls| Critique[Critique Agent]
    Orch -->|@tool calls| Reporter[Reporter Agent<br/>Claude 3.5 Sonnet]

    Searcher -->|MCP Protocol| Gateway[AgentCore Gateway<br/>with Cognito OAuth]
    Analyzer -->|MCP Protocol| Gateway

    Gateway -->|Invoke| SearchArxiv[search_arxiv<br/>Lambda]
    Gateway -->|Invoke| SearchSemantic[search_semantic_scholar<br/>Lambda]
    Gateway -->|Invoke| AcquirePaper[acquire_paper<br/>Lambda]
    Gateway -->|Invoke| ExtractContent[extract_content<br/>Lambda]
    Gateway -->|Invoke| PreprocessText[preprocess_text<br/>Lambda]

    SearchArxiv -->|Cache Results| S3[Amazon S3<br/>Paper Cache & Reports]
    SearchSemantic -->|Cache Results| S3
    ExtractContent -->|Store Content| S3

    Orch -->|Maintain State| State[ToolContext State<br/>research_plan, analyses,<br/>critique_results, etc.]

    Runtime -->|Final Report| User

    style Runtime fill:#FF9900
    style Gateway fill:#FF9900
    style Orch fill:#4A90E2
    style Planner fill:#7B68EE
    style Searcher fill:#7B68EE
    style Analyzer fill:#7B68EE
    style Critique fill:#7B68EE
    style Reporter fill:#7B68EE
    style SearchArxiv fill:#50C878
    style SearchSemantic fill:#50C878
    style AcquirePaper fill:#50C878
    style ExtractContent fill:#50C878
    style PreprocessText fill:#50C878
```

**Key Architecture Components:**

1. **User Interface (Streamlit):** Provides chat-based interaction and real-time visibility into agent execution phases.

2. **AgentCore Runtime:** AWS managed service that hosts and executes all Strands agents, handling scaling, state management, and agent lifecycle.

3. **Orchestrator Agent:** The central coordinator that manages workflow phases and delegates to specialist agents using the `@tool` decorator pattern.

4. **Specialist Agents:** Five domain-specific agents (Planner, Searcher, Analyzer, Critique, Reporter) that are invoked as tools by the orchestrator.

5. **AgentCore Gateway:** Secure MCP endpoint that provides authenticated access to Lambda tools, protected by Cognito OAuth.

6. **Lambda Tools:** Five deterministic functions that perform specific tasks (search, acquire, extract, preprocess) without reasoning capabilities.

7. **Amazon S3:** Object storage for caching paper content and storing final reports.

8. **State Management:** Built-in Strands ToolContext API maintains workflow state across agent invocations.

**Data Flow:**

1. User submits research query via Streamlit interface
2. Query is sent to AgentCore Runtime, invoking the orchestrator entrypoint
3. Orchestrator calls `planner_tool` to create research plan
4. Orchestrator calls `searcher_tool`, which invokes Lambda tools via Gateway to find papers
5. Orchestrator calls `analyzer_tool`, which invokes Lambda tools via Gateway to extract and analyze content
6. Orchestrator calls `critique_tool` to validate research quality
7. If revisions needed, orchestrator loops back to analysis phase
8. Once approved, orchestrator calls `write_report_section_tool` multiple times to generate report sections
9. Orchestrator calls `finalize_report_tool` to assemble complete report
10. Final report is returned to user via Streamlit interface
