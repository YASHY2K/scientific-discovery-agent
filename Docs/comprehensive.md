# Comprehensive System Architecture Explanation for the Autonomous Research Agent

Let me walk you through this architecture as if we're planning to build it together, explaining every service choice and how each piece contributes to the whole system. Think of this as building a sophisticated research team, but instead of humans, we're using AI agents that can work autonomously while giving us complete visibility into their thought process.

## Part 1: Executive Summary and Core Framework Choice
The goal of this project is to create a fully autonomous system that can conduct academic research without human intervention. When a user asks something like "Research the latest advances in Tree of Thoughts prompting," the system should independently find relevant papers, analyze them, critique its own work, and produce a comprehensive research report.

We're choosing **AWS Strands Agents SDK** as our core framework because it recently reached version 1.0 in July 2025, making it production-ready for this hackathon. The beauty of Strands is that it takes a model-driven approach, meaning we can build sophisticated AI agents with minimal code while maintaining full control over their behavior. It also natively supports something called the Agent-to-Agent (A2A) protocol, which is crucial for our multi-agent design.

The technology stack centers on three pillars:
- **AWS Strands Agents SDK** for orchestration
- **Amazon Bedrock AgentCore** for production infrastructure  
- **Claude 3.5 Sonnet** as the reasoning engine for all our agents

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

## Part 3: AWS Services Architecture
Now let's detail every AWS service we'll use and exactly what it does.

### Lambda Functions Required

We need seven primary Lambda functions in total:

#### Lambda 1: Main Agent Orchestrator Lambda
- **Function name:** `research-agent-orchestrator`
- **Memory:** 3008 MB (maximum for best performance)
- **Timeout:** 15 minutes
- **Purpose:** This is the heavyweight function that hosts all six Strands agents (the orchestrator plus five specialists). It:
  - Initializes agent instances
  - Manages agent-to-agent communication
  - Processes incoming research requests
  - Handles WebSocket connections for real-time updates
  - Coordinates the entire workflow
  - Streams agent thoughts to the frontend

#### Lambda 2: WebSocket Handler Lambda
- **Function name:** `research-websocket-handler`
- **Memory:** 512 MB
- **Timeout:** 30 seconds
- **Purpose:** Manages WebSocket connections for the Glass Box transparency feature. It:
  - Handles connection establishment and teardown
  - Routes messages between frontend and backend
  - Maintains connection state in DynamoDB
  - Enables bidirectional communication for user feedback

#### Lambda 3: ArXiv Search Tool Lambda
- **Function name:** `arxiv-search-tool`
- **Memory:** 512 MB
- **Timeout:** 30 seconds
- **Purpose:** A deterministic tool that searches arXiv for papers. It:
  - Executes searches against the arXiv API
  - Returns consistent results for identical queries
  - Provides paper metadata including titles, authors, abstracts, and PDF URLs

#### Lambda 4: PDF Text Extractor Lambda
- **Function name:** `pdf-extractor-tool`
- **Memory:** 1024 MB
- **Timeout:** 60 seconds
- **Purpose:** Extracts text from PDF papers. It:
  - Downloads PDFs from URLs
  - Extracts text from all pages
  - Implements caching to avoid reprocessing the same PDF
  - Stores extracted text in S3 for future use

#### Lambda 5: Semantic Search Lambda
- **Function name:** `semantic-search-tool`
- **Memory:** 768 MB
- **Timeout:** 30 seconds
- **Purpose:** Performs embedding-based similarity search. It:
  - Generates text embeddings using Amazon Titan
  - Calculates cosine similarity between queries and papers
  - Ranks papers by semantic relevance

#### Lambda 6: Citation Lookup Lambda
- **Function name:** `citation-lookup-tool`
- **Memory:** 512 MB
- **Timeout:** 30 seconds
- **Purpose:** Retrieves citation information for papers. It:
  - Integrates with citation databases
  - Returns citation counts
  - Identifies influential citations
  - Provides publication year data

#### Lambda 7: WebSocket Notification Relay Lambda
- **Function name:** `websocket-notification-relay`
- **Memory:** 256 MB
- **Timeout:** 10 seconds
- **Purpose:** Bridges SNS messages to WebSocket connections. It:
  - Subscribes to the SNS topic
  - Looks up active WebSocket connections from DynamoDB
  - Sends real-time updates to connected clients
### Storage Services

#### Amazon S3 - Two Buckets:

##### Cache Bucket (`research-agent-cache-{account-id}`)
- **Purpose:** Stores extracted PDF text to avoid reprocessing
- **Lifecycle rule:** 30-day expiration to manage costs
- **Access pattern:** Read-heavy after initial write
- **Used by:** PDF extractor Lambda

##### Reports Bucket (`research-agent-reports-{account-id}`)
- **Purpose:** Stores final research reports in Markdown format
- **Features:**
  - Provides persistent storage for completed research
  - Enables presigned URL generation for secure downloads
- **Used by:** Main orchestrator Lambda

#### Amazon DynamoDB - Two Tables:

##### Research Tasks Table (`research-tasks`)
- **Partition key:** `session_id` (string)
- **Purpose:** Stores research request details and status
- **Attributes:** user query, processing status, timestamps, report location
- **Features:** DynamoDB Streams enabled for event-driven processing

##### WebSocket Connections Table (`websocket-connections`)
- **Partition key:** `connection_id` (string)
- **Purpose:** Maps WebSocket connections to research sessions
- **Features:**
  - Enables targeted real-time updates to specific users
  - Tracks connection timestamps for cleanup
### API and Messaging Services

#### API Gateway REST API
- **Endpoint:** `POST /research`
- **Purpose:** 
  - Receives new research requests from the frontend
  - Returns session IDs for tracking
  - Triggers the main orchestrator Lambda
  - Handles authentication if needed

#### API Gateway WebSocket API
- **Routes:** `$connect`, `$disconnect`, `$default`
- **Purpose:**
  - Maintains persistent connections during research
  - Enables real-time bidirectional communication
  - Streams agent thoughts and actions to frontend
  - Allows user interactions during processing

#### Amazon SNS
- **Topic:** `research-agent-updates`
- **Purpose:**
  - Publishes agent activity events
  - Decouples event generation from delivery
  - Enables fan-out to multiple consumers
  - Bridges Lambda execution to WebSocket delivery
### AI/ML Services

#### Amazon Bedrock
- **Claude 3.5 Sonnet:** Powers all agent reasoning (6 agent instances)
- **Amazon Titan Embeddings V2:** Generates embeddings for semantic search
- **Access methods:** 
  - `InvokeModel` for single requests
  - `InvokeModelWithResponseStream` for streaming

### Supporting Services

#### AWS IAM
- Creates service roles for each Lambda function
- **Grants specific permissions:**
  - Bedrock access for agent Lambda
  - S3 access for storage operations
  - DynamoDB access for state management
  - SNS publish permissions for notifications

#### Amazon CloudWatch
- **Log Groups:** One per Lambda function with 2-week retention
- **Metrics:** Tracks invocations, errors, duration, throttles
- **Alarms:** Monitors for failures and performance issues
- **X-Ray:** Provides distributed tracing for debugging

#### AWS Lambda Layers
- **Dependencies Layer:** Contains Strands Agents SDK, boto3, arxiv library, PyPDF2, and other Python packages
- **Benefit:** Shared across multiple Lambda functions to reduce deployment size
## Part 4: Workflow Execution Details

Let me walk you through exactly what happens when a user submits a research request, step by step.

### Step 1: Request Initiation
The user types "Research Tree of Thoughts papers" in the web interface and clicks submit. The frontend sends a POST request to API Gateway's `/research` endpoint. API Gateway triggers the main orchestrator Lambda with the request payload.

### Step 2: Session Creation
The orchestrator Lambda generates a unique session ID and creates an entry in the DynamoDB `research-tasks` table with status "processing". It initializes all six agent instances and establishes the WebSocket connection reference.

### Step 3: Orchestrator Activation
The orchestrator agent receives the research query and begins reasoning. It thinks: "This is about Tree of Thoughts, a prompting technique. I need to create a research plan first." It decides to engage the Planner Agent.

### Step 4: Planning Phase
The orchestrator invokes the Planner Agent through the A2A protocol. The Planner reasons about the topic and creates a structured plan:
- Search for foundational papers
- Look for recent implementations
- Identify key authors
- Analyze different variations

The plan is returned to the orchestrator.

### Step 5: Literature Discovery
The orchestrator engages the Searcher Agent with the plan. The Searcher:
- Makes multiple calls to the `arxiv-search-tool` Lambda with queries like "Tree of Thoughts prompting," "ToT reasoning LLM," and author-specific searches
- Evaluates results and may refine queries for each search
- Calls the `semantic-search-tool` Lambda to rank papers by relevance

### Step 6: Deep Analysis
For each relevant paper (say 10 papers), the orchestrator engages the Analyzer Agent. The Analyzer:
- Calls the `pdf-extractor-tool` Lambda to get paper text (which checks S3 cache first)
- Reads each paper and extracts key methodologies
- Identifies the novel ToT algorithm variations
- Compares implementation details
- Creates structured summaries for each paper

### Step 7: Quality Control Loop
The orchestrator engages the Critique Agent with all the analysis. The Critique evaluates the work and might say: 

> "Good coverage of foundational work, but missing recent applications in code generation. Also, the comparison between ToT and CoT needs more detail." 

It returns a "REVISE" status with specific feedback.

### Step 8: Iterative Improvement
Based on the critique, the orchestrator:
- Re-engages the Searcher to find papers on "Tree of Thoughts code generation"
- Has the Analyzer process these new papers
- Asks the Analyzer to expand the ToT vs CoT comparison

This loop continues until the Critique returns "APPROVE."

### Step 9: Report Generation
With approval obtained, the orchestrator engages the Reporter Agent. The Reporter compiles everything into a comprehensive report with:
- Executive summary
- Methodology review
- Comparative analysis
- Future directions
- Proper citations

The report is formatted in Markdown.

### Step 10: Storage and Delivery
The orchestrator:
- Stores the final report in S3
- Updates DynamoDB with status "completed" and the S3 location
- Sends a final notification through WebSocket that the research is complete with a download link

## Part 5: Glass Box Transparency System

The Glass Box system provides real-time visibility into what the AI agents are thinking and doing. Here's how it works end-to-end:

### Event Generation
Every time an agent thinks, makes a decision, or calls a tool, it generates an event. These events include:
- Agent name
- Timestamp
- Action type (`thinking`, `tool_call`, `tool_result`)
- The actual thought process
- Any relevant data

### Event Publishing
Each event is published to the SNS topic `research-agent-updates` with the session ID as a message attribute.

### Event Relay
SNS triggers the `websocket-notification-relay` Lambda, which:
- Looks up the WebSocket connection ID for this session from DynamoDB
- Sends the event through API Gateway WebSocket to the connected client

### Frontend Display
The React frontend receives these events and displays them in a timeline. Users see:
- **Which agent is active** (color-coded)
- **What the agent is thinking** ("I need to search for more recent papers")
- **What tools are being called** ("Invoking arxiv_search_tool")
- **What results are returned** (collapsible JSON views)

This transparency builds trust and helps users understand how the AI reaches its conclusions.

## Part 6: Production Infrastructure Considerations

### Scalability
- **Serverless architecture** scales automatically
- **Lambda** can handle thousands of concurrent research sessions
- **DynamoDB and S3** scale infinitely with demand
- **API Gateway** automatically load balances requests
- **Only limit:** Bedrock API rate limits, which can be managed with request queuing

### Reliability
- **State persistence:** DynamoDB ensures system can recover from Lambda timeouts
- **S3 durability:** 99.999999999% durability for reports
- **Multi-AZ deployments** ensure availability
- **CloudWatch alarms** alert on failures

### Cost Optimization
- **Pay-per-use pricing** means zero cost when idle
- **PDF text caching** in S3 reduces repeated Bedrock calls
- **30-day lifecycle** on cache prevents infinite storage growth
- **Lambda memory** is right-sized for each function

### Security
- **Minimal IAM permissions** for each Lambda
- **Private S3 buckets** with presigned URLs for access
- **API Gateway** can implement Cognito authentication
- **Encryption** at rest and in transit for all data
- **VPC endpoints** can be used for private Bedrock access

## Communication Patterns

The system uses three distinct communication patterns:

### 1. Synchronous Request-Response
Used for initial research submission and final report retrieval through the REST API.

### 2. Asynchronous Pub-Sub
Agent events flow through SNS for decoupled real-time updates.

### 3. Agent-to-Agent Protocol
The orchestrator communicates with specialists through Strands A2A, treating intelligent agents as callable tools while preserving their autonomy.

---

## Conclusion

This architecture creates a sophisticated, transparent, and scalable research system where AI agents collaborate like a human research team, but with perfect memory, infinite patience, and complete visibility into their reasoning process. The serverless infrastructure ensures we only pay for what we use while maintaining the ability to handle massive scale when needed.