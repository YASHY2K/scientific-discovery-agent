Requirements Document - Scientific Discovery Agent
AWS Strands Agents SDK Implementation
Introduction

This specification defines the requirements for implementing a multi-agent research system using the AWS Strands Agents SDK for the AWS AI Agent Global Hackathon. The system will create specialized Strands agents that collaborate through the SDK's conversation management system to conduct academic research efficiently within hackathon constraints.
Strands SDK Architecture Constraints

    Agent Communication: Agents communicate through Strands conversation context, not direct API calls
    Tool Access: Each agent is configured with specific tools via Strands agent definition
    Memory Management: Conversation state managed by Strands SDK, with session limits
    Error Handling: Strands SDK handles agent failures and retries automatically
    Token Management: Individual agent conversations are tracked separately by Strands

System Constraints

    Budget: $100 AWS credits maximum
    Timeline: 25 days to working demo
    Demo Duration: 3-minute demonstration requirement
    API Limits: ArXiv (3 requests/sec), Semantic Scholar (100 requests/sec)
    Processing Scope: Maximum 10 paper abstracts + 3 full papers per research query
    Response Time: Target <3 minutes for complete research workflow
    Strands Limits: Maximum 2 active agent conversations simultaneously
    Token Budget: 20,000 tokens total per research session across all agents

Tool Function Specifications
Strands Agent Definitions

    search_arxiv: Query ArXiv database with keywords, returns paper metadata
    search_semantic_scholar: Query Semantic Scholar with keywords, returns paper metadata
    acquire_paper: Download full paper content using paper ID or DOI
    extract_content: Extract text content from PDF papers
    preprocess_text: Clean and structure extracted text for analysis

SearcherAgent

    Tools: search_arxiv, search_semantic_scholar, acquire_paper, extract_content
    Role: Find and retrieve relevant academic papers
    Input: Research query from user or structured plan from PlannerAgent
    Output: List of papers with metadata and content

AnalyzerAgent

    Tools: preprocess_text, extract_content
    Role: Analyze paper content and synthesize findings
    Input: Papers and content from SearcherAgent
    Output: Research insights and synthesis

PlannerAgent (Optional - Complex Queries Only)

    Tools: None (reasoning only)
    Role: Break down complex research queries into focused search strategies
    Input: Complex user research query
    Output: Structured search plan for SearcherAgent

Requirements
Requirement 1: Strands Agent Communication System [MVP]

User Story: As a researcher, I want Strands agents to collaborate seamlessly through the SDK's conversation system, so that my research query is handled efficiently by specialized agents.
Acceptance Criteria

    WHEN a research query is submitted THEN the Strands system SHALL route it to the appropriate first agent (SearcherAgent for simple queries, PlannerAgent for complex queries)
    WHEN an agent completes its task THEN it SHALL pass results to the next agent through Strands conversation context
    WHEN agents communicate THEN they SHALL use structured JSON objects in conversation messages for data consistency
    WHEN the research workflow is complete THEN the final agent SHALL provide results in the conversation context accessible to the frontend
    IF an agent encounters an error THEN Strands SDK SHALL handle retry logic according to configured policies

Technical Specifications:

    Agent Handoff Protocol: JSON objects with standardized schemas passed in conversation context
    Conversation Flow: User → SearcherAgent → AnalyzerAgent → User (simple queries)
    Complex Flow: User → PlannerAgent → SearcherAgent → AnalyzerAgent → User
    Error Recovery: Configured at Strands agent level with 2 retry attempts maximum

Requirement 2: SearcherAgent Implementation [MVP]

User Story: As a researcher, I want a Strands agent to intelligently search academic databases and find the most relevant papers, so that I get high-quality results within API limits.
Acceptance Criteria

    WHEN receiving a research query THEN the SearcherAgent SHALL analyze the query and select appropriate database (ArXiv OR Semantic Scholar)
    WHEN conducting searches THEN the SearcherAgent SHALL use its configured search tools with exponential backoff for rate limiting
    WHEN search results are returned THEN the SearcherAgent SHALL rank papers by relevance and recency
    WHEN top papers are identified THEN the SearcherAgent SHALL acquire abstracts for top 10 and full content for top 3 papers
    IF API limits are hit THEN the SearcherAgent SHALL implement retry logic and inform the user via conversation context
    WHEN search is complete THEN the SearcherAgent SHALL pass structured paper data to AnalyzerAgent through conversation context

Strands Configuration:

    Assigned Tools: search_arxiv, search_semantic_scholar, acquire_paper, extract_content
    Token Limit: 8,000 tokens per conversation
    Retry Policy: 2 attempts with exponential backoff
    Output Format: JSON array in conversation context with paper objects

Requirement 3: AnalyzerAgent Implementation [MVP]

User Story: As a researcher, I want a Strands agent to analyze paper content and extract key insights efficiently, so that I can understand the research landscape quickly.
Acceptance Criteria

    WHEN receiving paper data from SearcherAgent THEN the AnalyzerAgent SHALL process papers using its preprocess_text and extract_content tools
    WHEN analyzing papers THEN the AnalyzerAgent SHALL identify key findings, methodologies, and contributions for each paper
    WHEN processing multiple papers THEN the AnalyzerAgent SHALL synthesize findings and identify common themes and contradictions
    WHEN analysis is complete THEN the AnalyzerAgent SHALL generate a concise research brief (300-500 words)
    IF papers exceed token limits THEN the AnalyzerAgent SHALL prioritize the 3 most recent papers for deep analysis
    WHEN synthesis is done THEN the AnalyzerAgent SHALL provide final results in conversation context for frontend consumption

Strands Configuration:

    Assigned Tools: preprocess_text, extract_content
    Token Limit: 10,000 tokens per conversation
    Processing Strategy: Chunk large papers into 2000-token segments
    Output Format: Structured research brief with citations in conversation context

Requirement 4: PlannerAgent Implementation [Extended - Complex Queries Only]

User Story: As a researcher, I want a Strands agent to break down complex research queries into focused search strategies, so that broad topics are handled systematically.
Acceptance Criteria

    WHEN a complex research query is received THEN the PlannerAgent SHALL identify key research dimensions and sub-topics
    WHEN creating a research plan THEN the PlannerAgent SHALL specify search strategy and focus areas for SearcherAgent
    WHEN planning is complete THEN the PlannerAgent SHALL pass structured guidance to SearcherAgent through conversation context
    WHEN the query spans multiple domains THEN the PlannerAgent SHALL prioritize the most relevant domain
    IF the query is unclear THEN the PlannerAgent SHALL make reasonable assumptions and document them

Strands Configuration:

    Assigned Tools: None (reasoning only)
    Token Limit: 2,000 tokens per conversation
    Activation Trigger: Queries >100 words OR containing multiple research questions
    Output Format: JSON plan object passed to SearcherAgent

Requirement 5: User Interaction and Conversation Management [MVP]

User Story: As a researcher, I want to interact with the Strands agent system through natural conversation, so that I can guide the research process and ask follow-up questions.
Acceptance Criteria

    WHEN a user submits a research query THEN the Strands system SHALL route it to the appropriate agent based on query complexity
    WHEN users ask follow-up questions THEN the system SHALL route questions to the agent with relevant context
    WHEN agents provide intermediate results THEN users SHALL be able to request clarifications or modifications
    WHEN conversation becomes lengthy THEN the system SHALL summarize previous context to stay within token limits
    IF users want to start a new research topic THEN the system SHALL create a new conversation session

Strands Configuration:

    Conversation Management: Strands SDK handles conversation routing and context
    Session Limits: Maximum 15 minutes per research session
    Context Management: Last 5 exchanges preserved in conversation context
    Multi-turn Support: Users can refine queries and request additional analysis

Requirement 6: Real-time Progress Streaming [MVP]

User Story: As a researcher, I want to see real-time progress of agent work, so that I understand what's happening and can provide guidance when needed.
Acceptance Criteria

    WHEN agents begin work THEN the system SHALL stream status updates to the frontend via WebSocket
    WHEN agents complete tasks THEN the system SHALL send completion notifications with summaries
    WHEN agents encounter issues THEN the system SHALL provide transparent error messages
    WHEN agent handoffs occur THEN the system SHALL show which agent is taking over
    IF WebSocket connection fails THEN the system SHALL store updates for retrieval

Technical Specifications:

    Streaming Source: Strands SDK conversation events via SNS/WebSocket
    Update Types: agent_started, task_progress, agent_completed, handoff_occurred
    Message Format: JSON with timestamp, agent_name, status, and message
    Fallback: REST API endpoint for missed updates

Requirement 7: Interactive Conversation System [Extended]

User Story: As a researcher, I want to ask follow-up questions during the research process, so that I can guide the analysis toward my specific interests.
Acceptance Criteria

    WHEN a user asks a follow-up question THEN the system SHALL determine appropriate agent using intent classification
    WHEN agents receive user input THEN they SHALL incorporate guidance into current analysis without full restart
    WHEN conversation context changes THEN the system SHALL maintain only the last 5 exchanges in memory to control costs
    IF user requests require new searches THEN the system SHALL respect cumulative API limits
    WHEN interactive sessions exceed 15 minutes THEN the system SHALL warn about potential timeout and cost limits

Technical Specifications:

    Intent Classification: Simple keyword matching for demo purposes
    State Management: In-memory conversation history (max 5 exchanges)
    Context Preservation: JSON state object passed between agent calls

Requirement 8: Real-time Transparency and Streaming [MVP]

User Story: As a researcher, I want to see what each agent is doing in real-time, so that I can understand the research process and provide guidance.
Acceptance Criteria

    WHEN agents perform actions THEN the system SHALL stream updates via WebSocket within 2 seconds
    WHEN agents start processing THEN the system SHALL send status updates with agent name, action, and estimated completion time
    WHEN agents complete tasks THEN the system SHALL send completion notifications with summary of work done
    WHEN errors occur THEN the system SHALL send error notifications with plain English explanations
    IF WebSocket connection fails THEN the system SHALL store updates for retrieval via REST API
    WHEN research is complete THEN the system SHALL send final summary with links to all generated outputs

Technical Specifications:

    WebSocket Protocol: JSON messages with standardized schema
    Update Frequency: Maximum 1 update per 5 seconds per agent to avoid spam
    Message Types: status_update, completion_notification, error_notification, final_summary
    Fallback Storage: Redis cache with 1-hour TTL

Requirement 9: Memory and State Management [Extended]

User Story: As a researcher, I want the system to remember our research context throughout the session, so that agents can build on previous work.
Acceptance Criteria

    WHEN a research session starts THEN the system SHALL create persistent memory store with session ID
    WHEN agents discover information THEN the system SHALL store findings in shared memory with timestamps
    WHEN memory approaches limits THEN the system SHALL prioritize recent findings and user feedback
    WHEN sessions exceed 1 hour THEN the system SHALL archive old data to prevent memory bloat

Technical Specifications:

    Memory Store: Redis with structured keys (session:agent:type:data)
    Data Retention: 4 hours for active sessions, 24 hours for completed sessions
    Memory Limits: 10MB per session maximum (much more realistic for hackathon)

Requirement 10: Error Handling and Resilience [Extended]

User Story: As a researcher, I want the system to handle failures gracefully, so that I can get useful results even when some services fail.
Acceptance Criteria

    WHEN external APIs return errors THEN agents SHALL log errors and continue with available data
    WHEN Bedrock calls fail THEN agents SHALL implement exponential backoff with maximum 3 retries
    WHEN tool functions timeout THEN agents SHALL provide partial results and clear error messages
    WHEN critical components fail THEN the system SHALL provide graceful degradation and suggest manual alternatives
    IF session state is corrupted THEN the system SHALL offer to restart with preserved user inputs

Technical Specifications:

    Retry Logic: Exponential backoff with jitter (1s, 2s, 4s intervals)
    Circuit Breaker: Disable failing services for 5 minutes after 3 consecutive failures
    Graceful Degradation: Clearly communicate reduced functionality to users
    Error Logging: CloudWatch with structured error messages for debugging

Success Criteria for Hackathon Demo
Technical Demonstration

    Complete workflow from query to insights in <5 minutes
    Real-time agent progress visible in UI
    Handle at least 10 papers (abstracts) with 3 deep analyses
    Generate coherent research brief with proper citations
    Demonstrate error recovery (simulated API failure)

User Experience

    Clear, engaging UI showing agent collaboration
    Responsive WebSocket updates
    Downloadable research outputs
    Intuitive interaction flow

Cost Management

    Complete demo runs under $5 in AWS costs
    API calls stay within rate limits
    Efficient token usage in Bedrock calls

🔬 Scientific Discovery Agent - Redesigned for Hackathon
Core Concept: Research Assistant, Not Paper Generator

Position: An intelligent research assistant that helps researchers explore, synthesize, and understand literature - inspired by NotebookLM's approach but specialized for academic research.

Key Insight: Rather than generating complete papers, focus on being an invaluable research companion that accelerates the discovery and synthesis phase.
NotebookLM-Inspired Interface Design
Three-Panel Layout

Taking inspiration from NotebookLM's three core areas: Sources, Chat, and Studio:

1. SOURCES Panel (Left)

    Upload research prompts/topics
    Display discovered papers with thumbnails
    Show search progress with your Step Functions workflow
    Filter papers by relevance, date, citation count
    Visual tags for different research areas

2. RESEARCH CHAT Panel (Center)

    Interactive conversation with your multi-agent system
    Real-time updates as each agent completes its work
    Ask follow-up questions about findings
    Request deeper analysis on specific topics
    Generated summary of all sources with the ability to ask questions

3. INSIGHTS STUDIO Panel (Right)

    Generate different output formats:
        Research Brief: Executive summary with key findings
        Literature Map: Visual connections between papers
        Research Gaps: Identified opportunities
        Methodology Comparison: Side-by-side analysis
        Citation Network: Interactive graph of paper relationships

User Experience Flow
Input Phase

User enters: "I'm exploring CRISPR-Cas9 delivery mechanisms for treating muscular dystrophy"

Discovery Phase (Visual Workflow)

    Step Functions visualization shows real-time progress
    PlannerAgent creates research strategy
    SearchAgent finds relevant papers
    User can see live updates: "Found 47 papers from PubMed, 23 from arXiv..."

Interactive Analysis Phase

User can:

    Ask: "What are the most promising delivery methods mentioned?"
    Request: "Compare the efficiency rates across different studies"
    Explore: "Show me papers that mention safety concerns"
    Dive deeper: "Analyze the methodology of the top 3 papers"

Output Generation

Instead of a single long paper, generate modular insights:

    Executive Summary (2-3 paragraphs)
    Key Findings Grid (visual comparison table)
    Research Landscape Map (visual network of topics)
    Methodology Insights (what approaches are trending)
    Future Directions (identified gaps and opportunities)
    Curated Bibliography (top papers with relevance scores)

Technical Implementation for Hackathon
Simplified Architecture (Budget-Conscious)

Frontend (React) 
    ↓
API Gateway → Step Functions
    ↓
Lambda Functions (5 agents):
    1. PlannerAgent (creates research strategy)
    2. SearchAgent (queries arXiv/PubMed APIs)
    3. AnalysisAgent (synthesizes findings)
    4. CritiqueAgent (validates and scores relevance)
    5. InsightsAgent (generates visual summaries)
    ↓
Real-time updates via WebSocket

Cost-Effective Features

    Free APIs: arXiv, PubMed, CORE (open access papers)
    Smart Caching: Store search results to avoid re-processing
    Batch Processing: Process multiple papers efficiently
    Progressive Loading: Show results as they come in

Demo Scenario for Hackathon
30-Second Hook

"Watch our AI research team discover, analyze, and synthesize the latest CRISPR research in real-time"
3-Minute Demo Flow

    [0:00-0:30] Enter research question, show three-panel interface
    [0:30-1:30] Watch Step Functions workflow execute, agents collaborate
    [1:30-2:30] Interact with Chat panel, ask follow-up questions
    [2:30-3:00] Show generated insights: visual map, key findings, research gaps

Compelling Demo Data Points

    "Processed 127 papers in 2 minutes"
    "Identified 5 emerging delivery methods not mentioned in reviews"
    "Found 3 critical safety studies from the last 6 months"
    "Generated comprehensive research brief with 47 citations"

Value Propositions
For Researchers

    Time Savings: "What used to take weeks now takes minutes"
    Discovery: Find papers and connections you might miss
    Synthesis: Get structured insights, not just paper dumps
    Validation: AI peer review catches gaps and biases

For the Hackathon

    Technical Excellence: Multi-agent orchestration with Step Functions
    Real Impact: Addresses genuine research bottlenecks
    Visual Appeal: Interactive workflow and insight generation
    Scalable: Serverless architecture handles varying loads

Differentiation from Existing Tools

Feature	Semantic Scholar	Elicit	Research Rabbit	Your Agent
Multi-agent workflow	❌	❌	❌	✅
Real-time collaboration	❌	❌	❌	✅
Visual workflow	❌	❌	✅	✅
AI peer review	❌	❌	❌	✅
Interactive chat	❌	✅	❌	✅
Multiple output formats	❌	✅	❌	✅

Success Metrics for Demo
Technical Metrics

    Step Functions execution success rate: >95%
    Average processing time: <3 minutes for 50+ papers
    WebSocket real-time updates: <1 second latency
    Citation accuracy: >90% verifiable links

User Experience Metrics

    Interface responsiveness
    Clarity of generated insights
    Usefulness of discovered connections
    Quality of interactive Q&A

Post-Hackathon Evolution Path
Phase 1: Core research assistant
Phase 2: Add collaborative features (team notebooks)
Phase 3: Integrate with reference managers
Phase 4: Add writing assistance for drafts
Phase 5: Full research workflow automation

This positions your hackathon project as the foundation of a comprehensive research platform, not just a one-off tool.
