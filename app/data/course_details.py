"""
Detailed course content mapping for all seeded SmartReco courses.
Provides course-specific learning outcomes, prerequisites, target audience,
tools/technologies, estimated effort, curriculum (modules and lessons),
practical final project, instructor bio, and FAQs.
"""

COURSE_DETAILS = {
    "introduction-to-agentic-ai": {
        "what_you_will_learn": [
            "Architect single-agent loops with goal decomposition and state tracking",
            "Define explicit tool interfaces with schema validation and error recovery",
            "Implement deterministic fallback logic when agent tool execution fails",
            "Measure agent task completion reliability using structured log telemetry",
            "Establish safe execution boundaries for automated system actions"
        ],
        "prerequisites": [
            "Basic proficiency in Python (functions, dictionaries, type hints)",
            "Understanding of REST APIs and JSON structure"
        ],
        "target_audience": [
            "Backend Engineers seeking to build reliable LLM-powered services",
            "AI Engineers moving beyond basic prompt wrappers to stateful agents",
            "Technical Product Managers evaluating agentic automation feasibility"
        ],
        "tools_used": ["Python 3.11", "LangGraph", "Pydantic", "FastAPI", "Qdrant"],
        "estimated_effort": "2.5 hours total (1.5 hrs/week over 2 weeks)",
        "curriculum": [
            {
                "title": "Module 1: Foundations of Goal-Driven AI",
                "description": "Deconstruct agentic architecture, control loops, and state machine models.",
                "lessons": [
                    {
                        "title": "Agent vs. Simple Completion Models",
                        "duration_minutes": 15,
                        "type": "Interactive Lecture",
                        "summary": "Compare deterministic linear prompts against iterative ReAct agent cycles."
                    },
                    {
                        "title": "Designing State Schema & Tool Boundaries",
                        "duration_minutes": 20,
                        "type": "Code Walkthrough",
                        "summary": "Model bounded state containers using Pydantic and explicit type annotations."
                    },
                    {
                        "title": "Building Your First Reasoning Loop",
                        "duration_minutes": 20,
                        "type": "Hands-on Exercise",
                        "summary": "Implement a 3-step decision loop with exit criteria and iteration limits."
                    }
                ]
            },
            {
                "title": "Module 2: Tool Integration & Safety Guardrails",
                "description": "Connect external functions while enforcing parameter contracts and safety boundaries.",
                "lessons": [
                    {
                        "title": "Defining Strict Tool Schemas",
                        "duration_minutes": 20,
                        "type": "Hands-on Exercise",
                        "summary": "Register search and database retrieval functions with strict runtime typing."
                    },
                    {
                        "title": "Handling Tool Execution Exceptions",
                        "duration_minutes": 25,
                        "type": "Lab Session",
                        "summary": "Gracefully handle API timeouts, missing data, and invalid arguments without crashing the loop."
                    },
                    {
                        "title": "Evaluating Agent Decision Drift",
                        "duration_minutes": 15,
                        "type": "Case Study",
                        "summary": "Audit decision traces to detect hallucinated parameters and ungrounded tool calls."
                    }
                ]
            }
        ],
        "final_project": {
            "title": "Autonomous Customer Support Triaging Agent",
            "description": "Build an agent that receives incoming customer tickets, queries a mock knowledge base using validated tools, categorizes issue severity, and produces a verified response draft."
        },
        "instructor_bio": "Maya Iyer is a Principal AI Systems Architect with over a decade of experience building enterprise automation pipelines. She previously led agentic infrastructure teams at CloudScale AI.",
        "faqs": [
            {
                "question": "Do I need access to paid LLM API keys to complete this course?",
                "answer": "No. The course includes mock client adapters compatible with local testing and standard Mesh endpoint configurations."
            },
            {
                "question": "How is this course different from prompt engineering guides?",
                "answer": "This course focuses on software engineering patterns—state management, tool schemas, and error boundaries—rather than prompt tuning tricks."
            },
            {
                "question": "Can I apply these patterns to non-OpenAI model providers?",
                "answer": "Yes! All architectural patterns taught are model-agnostic and rely on standard JSON schemas."
            }
        ]
    },
    "advanced-langgraph-workflows": {
        "what_you_will_learn": [
            "Design stateful, multi-step graphs using LangGraph state reducers",
            "Implement durable check-pointing for pause, resume, and human-in-the-loop steps",
            "Build parallel branch execution and conditional router nodes",
            "Handle transient node failures with backoff retry policies and safe rollback states",
            "Monitor graph execution flows using telemetry and node execution metadata"
        ],
        "prerequisites": [
            "Completion of 'Introduction to Agentic AI' or equivalent experience",
            "Strong understanding of async Python (`asyncio`) and state machines"
        ],
        "target_audience": [
            "Senior Software Engineers building complex LLM orchestration pipelines",
            "Data Engineers orchestrating multi-stage AI workflows"
        ],
        "tools_used": ["LangGraph", "Python 3.11", "Asyncio", "Sqlite/PostgreSQL", "LangChain"],
        "estimated_effort": "5 hours total (2.5 hrs/week over 2 weeks)",
        "curriculum": [
            {
                "title": "Module 1: LangGraph Architecture & State Machines",
                "description": "Master graph state definitions, custom node reducers, and flow control.",
                "lessons": [
                    {
                        "title": "State Reducers and Graph Topologies",
                        "duration_minutes": 30,
                        "type": "Deep Dive Lecture",
                        "summary": "Understand state immutability, state mutation keys, and reducer mechanics."
                    },
                    {
                        "title": "Constructing Conditional Routing Nodes",
                        "duration_minutes": 35,
                        "type": "Code Workshop",
                        "summary": "Build routing functions that evaluate confidence scores to branch execution paths."
                    },
                    {
                        "title": "Parallel Branch Merging & Fan-Out",
                        "duration_minutes": 40,
                        "type": "Hands-on Exercise",
                        "summary": "Execute parallel retrieval and evaluation nodes before aggregating results into a final state."
                    }
                ]
            },
            {
                "title": "Module 2: Durability, Checkpointing & Fault Tolerance",
                "description": "Integrate persistent state checkpoints for fault recovery and manual approvals.",
                "lessons": [
                    {
                        "title": "Database Checkpointers in Production",
                        "duration_minutes": 45,
                        "type": "Lab Session",
                        "summary": "Configure SQLite and Async SQLAlchemy checkpointers to persist thread state across restarts."
                    },
                    {
                        "title": "Implementing Human-in-the-Loop Interrupts",
                        "duration_minutes": 45,
                        "type": "Hands-on Exercise",
                        "summary": "Pause graph execution for human verification before high-risk database mutation steps."
                    },
                    {
                        "title": "Graph Recovery & Retry Policies",
                        "duration_minutes": 45,
                        "type": "System Design",
                        "summary": "Implement sub-graph error boundary traps and deterministic fallback nodes."
                    }
                ]
            }
        ],
        "final_project": {
            "title": "Self-Correcting Multi-Step Code Refactoring Graph",
            "description": "Design a 5-node LangGraph workflow that accepts code, executes static linting, identifies issues, invokes an LLM repair node, and re-tests until clean or max retries are reached."
        },
        "instructor_bio": "Jon Bell is a Lead Distributed Systems Engineer specializing in stateful workflow engine design. He has authored several production graph frameworks.",
        "faqs": [
            {
                "question": "Is LangGraph required for stateful agents, or can I use raw Python?",
                "answer": "While raw Python works for trivial loops, LangGraph provides production-grade state persistence, human interrupts, and branching control."
            },
            {
                "question": "Does this cover version 0.2+ of LangGraph?",
                "answer": "Yes, all lessons use modern LangGraph syntax with typed state dictionary reducers."
            }
        ]
    },
    "production-rag-systems": {
        "what_you_will_learn": [
            "Evaluate chunking strategies (semantic, recursive, hierarchical) for enterprise documents",
            "Implement hybrid search combining dense vector retrieval and sparse keyword indexing",
            "Build deterministic reranking and hallucination suppression pipelines",
            "Configure end-to-end evaluation metrics including context recall and grounding precision",
            "Mitigate vector store data drift with transactional vector outbox patterns"
        ],
        "prerequisites": [
            "Familiarity with vector embeddings and database queries",
            "Intermediate Python skill level"
        ],
        "target_audience": [
            "AI Platform Engineers scaling knowledge search infrastructure",
            "Full Stack Developers adding reliable semantic search to products"
        ],
        "tools_used": ["Qdrant", "Python", "FastAPI", "Tiktoken", "Ragas Evaluation Framework"],
        "estimated_effort": "6 hours total (3 hrs/week over 2 weeks)",
        "curriculum": [
            {
                "title": "Module 1: Document Processing & Retrieval Foundations",
                "description": "Optimize chunking, metadata enrichment, and indexing strategies.",
                "lessons": [
                    {
                        "title": "Semantic Chunking vs. Token Sliding Windows",
                        "duration_minutes": 40,
                        "type": "Interactive Lecture",
                        "summary": "Analyze chunk boundary impact on query context preservation and retrieval precision."
                    },
                    {
                        "title": "Enriching Metadata for Targeted Filtering",
                        "duration_minutes": 50,
                        "type": "Hands-on Exercise",
                        "summary": "Extract entity tags and hierarchy markers during ingestion to enable exact-match metadata filters."
                    },
                    {
                        "title": "Dense & Sparse Hybrid Retrieval Setup",
                        "duration_minutes": 60,
                        "type": "Lab Session",
                        "summary": "Combine vector similarity scores with BM25 keyword matching for optimal recall."
                    }
                ]
            },
            {
                "title": "Module 2: Reranking, Grounding & Evaluation",
                "description": "Ensure zero hallucination and high precision before answer generation.",
                "lessons": [
                    {
                        "title": "Cross-Encoder Reranking Pipelines",
                        "duration_minutes": 50,
                        "type": "Code Workshop",
                        "summary": "Implement secondary cross-encoder scoring to filter out top-K irrelevant chunks."
                    },
                    {
                        "title": "Grounding Validation & Citation Verification",
                        "duration_minutes": 50,
                        "type": "Hands-on Exercise",
                        "summary": "Build a citation check node that asserts every statement traces back to retrieved evidence."
                    },
                    {
                        "title": "Automated RAG Evaluation Suite",
                        "duration_minutes": 50,
                        "type": "System Design",
                        "summary": "Set up continuous offline evaluation benchmarking Faithfulness, Answer Relevance, and Context Precision."
                    }
                ]
            }
        ],
        "final_project": {
            "title": "Enterprise Technical Documentation RAG Service",
            "description": "Construct a production RAG backend that ingests multi-format tech docs, indexes them into Qdrant with outbox transactional sync, performs hybrid search, and serves grounded answers with verifiable source citations."
        },
        "instructor_bio": "Leena Das is a Senior Retrieval Systems Engineer with expertise in high-throughput vector search and domain-adapted semantic ranking.",
        "faqs": [
            {
                "question": "Which vector store is used during hands-on exercises?",
                "answer": "The course uses Qdrant, but all vector storage patterns apply equally to Pgvector or Pinecone."
            },
            {
                "question": "How do we handle large PDF or Markdown document ingestion?",
                "answer": "Module 1 covers specialized parser libraries and recursive layout-aware chunking."
            }
        ]
    },
    "multi-agent-orchestration": {
        "what_you_will_learn": [
            "Coordinate worker agents using supervisor, peer-to-peer, and hierarchical topologies",
            "Define explicit agent delegation contracts and structured payload interfaces",
            "Prevent infinite agent delegation loops with strict execution budgets",
            "Implement conflict resolution when worker agents produce contradictory outputs",
            "Trace multi-agent execution paths using span context propagation"
        ],
        "prerequisites": [
            "Understanding of single-agent loops and basic graph workflows",
            "Python async programming"
        ],
        "target_audience": [
            "Senior Backend Engineers building complex automated agent teams",
            "System Architects designing multi-domain automation systems"
        ],
        "tools_used": ["LangGraph", "Python 3.11", "FastAPI", "Pydantic", "OpenTelemetry"],
        "estimated_effort": "4.5 hours total (2.25 hrs/week over 2 weeks)",
        "curriculum": [
            {
                "title": "Module 1: Multi-Agent Topologies & Delegation Contracts",
                "description": "Structure agent hierarchy and handoff mechanisms.",
                "lessons": [
                    {
                        "title": "Supervisor vs. Peer Orchestration Patterns",
                        "duration_minutes": 35,
                        "type": "System Architecture",
                        "summary": "Analyze when centralized routing outperforms decentralized peer handoffs."
                    },
                    {
                        "title": "Defining Handoff Schemas & Memory Isolation",
                        "duration_minutes": 40,
                        "type": "Code Workshop",
                        "summary": "Build scoped memory buffers so specialized agents receive only relevant contextual history."
                    },
                    {
                        "title": "Execution Budgets & Infinite Loop Traps",
                        "duration_minutes": 35,
                        "type": "Hands-on Exercise",
                        "summary": "Enforce maximum delegation depths and time-to-live execution counters across agent boundaries."
                    }
                ]
            },
            {
                "title": "Module 2: Consensus, Error Propagation & Observability",
                "description": "Manage agent failures, consensus aggregation, and distributed tracing.",
                "lessons": [
                    {
                        "title": "Consensus Aggregation & Conflict Resolution",
                        "duration_minutes": 35,
                        "type": "Hands-on Exercise",
                        "summary": "Build a voter node that synthesizes responses from multiple domain-expert agents."
                    },
                    {
                        "title": "Graceful Fallback & Worker Replacement",
                        "duration_minutes": 35,
                        "type": "Lab Session",
                        "summary": "Handle worker agent timeout or invalid output by rerouting tasks to alternate nodes."
                    },
                    {
                        "title": "Distributed Tracing of Multi-Agent Runs",
                        "duration_minutes": 30,
                        "type": "Observability Lab",
                        "summary": "Propagate trace correlation IDs across agent calls to render clean visual trace graphs."
                    }
                ]
            }
        ],
        "final_project": {
            "title": "Automated Software Code Review Panel",
            "description": "Build a multi-agent system comprising a Security Auditor Agent, Performance Analyst Agent, and Style Guide Agent led by a Chief Reviewer Supervisor that delivers a consolidated code review report."
        },
        "instructor_bio": "Owen Carter is a Principal Distributed Systems Engineer who specializes in multi-agent microservice architecture and cloud orchestration.",
        "faqs": [
            {
                "question": "When should I use multi-agent systems instead of one big prompt?",
                "answer": "When tasks require distinct domain tools, isolated memory contexts, or specialized evaluation criteria that overwhelm single-prompt contexts."
            }
        ]
    },
    "python-for-beginners": {
        "what_you_will_learn": [
            "Master Python fundamentals: variables, control flow, functions, and data structures",
            "Read and write data safely using text files, JSON files, and path management",
            "Write clean modular code adhering to Python PEP 8 conventions",
            "Perform defensive programming using standard error handling (`try/except`)",
            "Write automated unit tests using Pytest to verify function behavior"
        ],
        "prerequisites": ["Basic computer operation skills. No prior coding experience required!"],
        "target_audience": [
            "Aspiring Developers starting their software journey",
            "Data Analysts, Marketers, and Researchers wanting to automate daily tasks"
        ],
        "tools_used": ["Python 3.11", "VS Code", "Pytest", "Standard Library"],
        "estimated_effort": "3 hours total (1.5 hrs/week over 2 weeks)",
        "curriculum": [
            {
                "title": "Module 1: Python Core Building Blocks",
                "description": "Learn syntax, data types, conditional branching, and loops.",
                "lessons": [
                    {
                        "title": "Variables, Primitive Types & Expressions",
                        "duration_minutes": 25,
                        "type": "Interactive Coding",
                        "summary": "Work with strings, integers, floats, booleans, and dynamic type conversion."
                    },
                    {
                        "title": "Control Structure: Conditionals & Loops",
                        "duration_minutes": 30,
                        "type": "Hands-on Exercise",
                        "summary": "Master `if/elif/else` decisions, `for` loops over sequences, and `while` loop conditions."
                    },
                    {
                        "title": "Functions, Arguments & Return Values",
                        "duration_minutes": 35,
                        "type": "Code Workshop",
                        "summary": "Write reusable functions with parameter defaults, keyword arguments, and docstrings."
                    }
                ]
            },
            {
                "title": "Module 2: Collections, File I/O & Unit Testing",
                "description": "Organize data into structures, interact with files, and write unit tests.",
                "lessons": [
                    {
                        "title": "Lists, Dictionaries & Sets",
                        "duration_minutes": 30,
                        "type": "Hands-on Exercise",
                        "summary": "Store and manipulate collections using list comprehension and dictionary lookups."
                    },
                    {
                        "title": "Reading & Writing File Data",
                        "duration_minutes": 30,
                        "type": "Practical Lab",
                        "summary": "Safely open, read, parse, and write JSON and CSV files using python context managers."
                    },
                    {
                        "title": "Writing Your First Pytest Test Suite",
                        "duration_minutes": 30,
                        "type": "Testing Lab",
                        "summary": "Write assertions and test cases to automatically verify your functions work as expected."
                    }
                ]
            }
        ],
        "final_project": {
            "title": "Personal Task & Expense CLI Tool",
            "description": "Build a command-line application that logs daily tasks/expenses, saves records to JSON files, calculates summaries, and includes automated unit tests."
        },
        "instructor_bio": "Ravi Shah is a passionate Software Educator who has introduced over 50,000 students to Python programming.",
        "faqs": [
            {
                "question": "Is any software installation required before starting?",
                "answer": "We guide you step-by-step through installing free tools: Python 3.11 and VS Code."
            }
        ]
    },
    "fastapi-backend-development": {
        "what_you_will_learn": [
            "Build asynchronous RESTful APIs using FastAPI and Pydantic validation models",
            "Implement dependency injection for session management and configuration injection",
            "Integrate Async SQLAlchemy 2.0 with SQLite/PostgreSQL databases",
            "Enforce security best practices: password hashing, JWT sessions, and CSRF protection",
            "Write comprehensive API integration tests with Pytest and AsyncClient"
        ],
        "prerequisites": [
            "Solid understanding of Python basics (functions, classes, async syntax)",
            "Basic understanding of HTTP verbs (GET, POST, PUT, DELETE)"
        ],
        "target_audience": [
            "Python Developers transitioning from synchronous frameworks to async FastAPI",
            "Full Stack Engineers looking for a clean, modern Python API stack"
        ],
        "tools_used": ["FastAPI", "Async SQLAlchemy", "Pydantic v2", "Alembic", "Pytest", "Uvicorn"],
        "estimated_effort": "4 hours total (2 hrs/week over 2 weeks)",
        "curriculum": [
            {
                "title": "Module 1: FastAPI Fundamentals & Pydantic Validation",
                "description": "Construct typed routing, validation schemas, and custom error handlers.",
                "lessons": [
                    {
                        "title": "Routing, Path Params & Query Validation",
                        "duration_minutes": 35,
                        "type": "Code Workshop",
                        "summary": "Define API endpoints with typed path parameters and Pydantic query filters."
                    },
                    {
                        "title": "Request Body Schemas & Field Validators",
                        "duration_minutes": 35,
                        "type": "Hands-on Exercise",
                        "summary": "Create nested input validation models with custom field constraints."
                    },
                    {
                        "title": "FastAPI Dependency Injection Architecture",
                        "duration_minutes": 40,
                        "type": "Deep Dive",
                        "summary": "Inject database sessions, user authentication, and global settings cleanly."
                    }
                ]
            },
            {
                "title": "Module 2: Async ORM Integration & Testing",
                "description": "Connect database models and write robust async tests.",
                "lessons": [
                    {
                        "title": "Async SQLAlchemy Setup & Alembic Migrations",
                        "duration_minutes": 40,
                        "type": "Lab Session",
                        "summary": "Map database models, configure session factories, and execute migration scripts."
                    },
                    {
                        "title": "Authentication & Authorization Guards",
                        "duration_minutes": 35,
                        "type": "Security Workshop",
                        "summary": "Protect endpoints with user password verification and session token checks."
                    },
                    {
                        "title": "API Integration Testing with Pytest",
                        "duration_minutes": 35,
                        "type": "Testing Lab",
                        "summary": "Write end-to-end integration tests using HTTPX AsyncClient against test databases."
                    }
                ]
            }
        ],
        "final_project": {
            "title": "Production-Ready E-Learning Content API",
            "description": "Design and test a modular FastAPI backend service managing users, content items, search indexing outboxes, and authenticated enrollment endpoints."
        },
        "instructor_bio": "Asha Menon is a Senior Backend Infrastructure Architect specializing in high-throughput async Python microservices.",
        "faqs": [
            {
                "question": "Does this course cover FastAPI version 0.100+ and Pydantic v2?",
                "answer": "Yes! All lessons use Pydantic v2 validation syntax and modern FastAPI best practices."
            }
        ]
    },
    "vector-databases-in-practice": {
        "what_you_will_learn": [
            "Design vector collection schemas with optimized distance metrics (Cosine, Dot, Euclidean)",
            "Structure vector payloads with typed metadata for efficient pre-filtering",
            "Manage outbox synchronization between SQL source of truth and Qdrant index",
            "Perform vector snapshot backups, index rebuilding, and orphan detection",
            "Diagnose retrieval latency and recall performance bottlenecks"
        ],
        "prerequisites": ["Python intermediate proficiency", "Basic knowledge of embeddings"],
        "target_audience": [
            "Data Engineers implementing production vector search infrastructure",
            "Backend Engineers adding semantic search capabilities"
        ],
        "tools_used": ["Qdrant", "Python", "SQLAlchemy", "FastAPI", "Docker"],
        "estimated_effort": "3 hours total (1.5 hrs/week over 2 weeks)",
        "curriculum": [
            {
                "title": "Module 1: Vector Indexing & Collection Design",
                "description": "Master point creation, embedding dimensions, and distance metrics.",
                "lessons": [
                    {
                        "title": "Embedding Spaces & Distance Metrics",
                        "duration_minutes": 25,
                        "type": "Lecture & Visualization",
                        "summary": "Compare Cosine, Dot product, and Euclidean distances for semantic similarity."
                    },
                    {
                        "title": "Qdrant Collection & Payload Schema Setup",
                        "duration_minutes": 30,
                        "type": "Hands-on Exercise",
                        "summary": "Initialize collections, set point vector sizes, and attach JSON payload fields."
                    },
                    {
                        "title": "Payload Indexing & Metadata Pre-Filtering",
                        "duration_minutes": 30,
                        "type": "Code Workshop",
                        "summary": "Build boolean, keyword, and range payload indexes to execute fast filtered queries."
                    }
                ]
            },
            {
                "title": "Module 2: Transactional Sync & Operational Health",
                "description": "Maintain vector index integrity with SQL outbox tables and reconciliation.",
                "lessons": [
                    {
                        "title": "The Transactional Vector Outbox Pattern",
                        "duration_minutes": 25,
                        "type": "Architecture Lab",
                        "summary": "Prevent database-vector drift using atomic SQL outbox queues."
                    },
                    {
                        "title": "Reconciliation & Orphan Point Deletion",
                        "duration_minutes": 30,
                        "type": "Practical Exercise",
                        "summary": "Write operational reconciliation scripts to detect and clean orphaned vector points."
                    },
                    {
                        "title": "Performance Tuning & Benchmark Analysis",
                        "duration_minutes": 25,
                        "type": "Performance Lab",
                        "summary": "Measure query QPS, indexing memory footprint, and recall accuracy."
                    }
                ]
            }
        ],
        "final_project": {
            "title": "Resilient Catalog Vector Search Service",
            "description": "Implement a complete vector index pipeline featuring an outbox synchronization background worker, metadata-filtered semantic search endpoint, and vector reconciliation audit script."
        },
        "instructor_bio": "Nikhil Rao is a Lead Data Infrastructure Engineer who has engineered large-scale vector search engines for enterprise clients.",
        "faqs": [
            {
                "question": "Can I run Qdrant locally without cloud accounts?",
                "answer": "Yes! The course demonstrates both embedded Qdrant local storage and containerized local Docker setups."
            }
        ]
    },
    "prompt-engineering-fundamentals": {
        "what_you_will_learn": [
            "Structure clear prompts with explicit role framing, context, and instruction boundaries",
            "Implement zero-shot, few-shot, and chain-of-thought prompt techniques",
            "Enforce structured JSON output generation using schema enforcement",
            "Build automated prompt evaluation benchmarks to measure response consistency",
            "Protect applications against prompt injection and adversarial input manipulation"
        ],
        "prerequisites": ["No prior coding required. Basic literacy with AI tools recommended."],
        "target_audience": [
            "Product Managers, Designers, and Content Strategists working with AI feature specs",
            "Software Developers standardizing system prompts in applications"
        ],
        "tools_used": ["Prompt Workbench", "Python", "JSON Schema", "Mesh API"],
        "estimated_effort": "2 hours total (1 hr/week over 2 weeks)",
        "curriculum": [
            {
                "title": "Module 1: Prompt Construction & Reasoning Patterns",
                "description": "Master prompt structure, framing, and multi-step reasoning techniques.",
                "lessons": [
                    {
                        "title": "Anatomy of an Effective System Prompt",
                        "duration_minutes": 20,
                        "type": "Interactive Workshop",
                        "summary": "Deconstruct role definitions, instructions, constraints, and delimiter formatting."
                    },
                    {
                        "title": "Few-Shot Examples & In-Context Learning",
                        "duration_minutes": 20,
                        "type": "Hands-on Exercise",
                        "summary": "Select and format representative input-output pairs to guide edge-case handling."
                    },
                    {
                        "title": "Chain-of-Thought & Step-by-Step Reasoning",
                        "duration_minutes": 20,
                        "type": "Practical Lab",
                        "summary": "Prompt models to output intermediate reasoning steps before reaching final decisions."
                    }
                ]
            },
            {
                "title": "Module 2: Structured Outputs & Robustness Testing",
                "description": "Generate machine-readable outputs and test against prompt attacks.",
                "lessons": [
                    {
                        "title": "Enforcing JSON Schema & Structured Outputs",
                        "duration_minutes": 20,
                        "type": "Code Exercise",
                        "summary": "Draft prompts that return strictly validated JSON structures for backend integration."
                    },
                    {
                        "title": "Defending Against Prompt Injections",
                        "duration_minutes": 10,
                        "type": "Security Case Study",
                        "summary": "Identify indirect prompt injections and implement input sanitization boundaries."
                    },
                    {
                        "title": "Building an Offline Prompt Evaluation Matrix",
                        "duration_minutes": 10,
                        "type": "Testing Workshop",
                        "summary": "Benchmark prompt prompt performance across a test set of 20 realistic scenarios."
                    }
                ]
            }
        ],
        "final_project": {
            "title": "Structured Product Review Extraction System",
            "description": "Design, evaluate, and harden a system prompt that ingests customer reviews, extracts sentiment scores, identifies key product tags, and formats the output into strict JSON."
        },
        "instructor_bio": "Sara Kim is an AI Interaction Designer and Prompt Engineer who consults on user-centered LLM applications.",
        "faqs": [
            {
                "question": "Is prompt engineering still relevant with smarter models?",
                "answer": "Yes! Clear task specification, output schemas, and security boundaries remain essential engineering requirements regardless of model capability."
            }
        ]
    },
    "ai-application-observability": {
        "what_you_will_learn": [
            "Instrument AI request telemetry: latency, token usage, cost, and error metrics",
            "Implement distributed context propagation across LLM calls and tool executions",
            "Set up LangSmith/OpenTelemetry tracing without locking into proprietary vendors",
            "Detect latency spikes, context window overflow, and rate-limit bottlenecks",
            "Establish alert thresholds for model regression and API budget bounds"
        ],
        "prerequisites": ["Basic understanding of web backend architectures and logging"],
        "target_audience": [
            "DevOps Engineers and Site Reliability Engineers monitoring AI services",
            "Backend Engineers building production AI pipelines"
        ],
        "tools_used": ["OpenTelemetry", "LangSmith", "Python", "FastAPI", "Prometheus"],
        "estimated_effort": "2.5 hours total (1.25 hrs/week over 2 weeks)",
        "curriculum": [
            {
                "title": "Module 1: Telemetry & Tracing Foundations",
                "description": "Capture logs, metrics, and execution spans for model calls.",
                "lessons": [
                    {
                        "title": "Metrics That Matter in AI Applications",
                        "duration_minutes": 25,
                        "type": "Lecture",
                        "summary": "Track time-to-first-token, total latency, token consumption, and failure rates."
                    },
                    {
                        "title": "Distributed Tracing with OpenTelemetry Spans",
                        "duration_minutes": 25,
                        "type": "Hands-on Exercise",
                        "summary": "Create nested span contexts around retrieval, model generation, and tool execution steps."
                    },
                    {
                        "title": "LangSmith Tracing Integration",
                        "duration_minutes": 25,
                        "type": "Code Workshop",
                        "summary": "Configure non-blocking trace exporters with zero application downtime fallback."
                    }
                ]
            },
            {
                "title": "Module 2: Diagnostics, Cost & Reliability Monitoring",
                "description": "Build operational dashboards, cost trackers, and failure alerts.",
                "lessons": [
                    {
                        "title": "Cost Tracking & Token Budget Governance",
                        "duration_minutes": 25,
                        "type": "Practical Lab",
                        "summary": "Calculate real-time cost attribution per user session and trigger budget caps."
                    },
                    {
                        "title": "Diagnosing Latency & Timeout Failure Modes",
                        "duration_minutes": 25,
                        "type": "Case Study",
                        "summary": "Use trace visualizers to pinpoint upstream API delays and slow retrieval queries."
                    },
                    {
                        "title": "Automated Reliability Guardrails & Alerting",
                        "duration_minutes": 25,
                        "type": "Ops Lab",
                        "summary": "Set up automated alerts for elevated error rates and model degradation."
                    }
                ]
            }
        ],
        "final_project": {
            "title": "AI Service Observability Dashboard & Exporter",
            "description": "Instrument a multi-step RAG FastAPI application with OpenTelemetry spans, token usage counters, and an admin diagnostics endpoint."
        },
        "instructor_bio": "Priya Nair is a Principal SRE with 12 years of experience managing infrastructure observability for high-scale microservices.",
        "faqs": [
            {
                "question": "Does this require paid observability software?",
                "answer": "No. The course uses open-source OpenTelemetry standards compatible with free local tools."
            }
        ]
    },
    "building-secure-ai-products": {
        "what_you_will_learn": [
            "Map trust boundaries between users, client apps, LLM models, and external tools",
            "Mitigate direct and indirect prompt injection attacks",
            "Enforce least-privilege tool access controls and input validation layers",
            "Prevent sensitive data leakage (PII, system credentials) in model responses",
            "Develop incident response plans for AI safety and security events"
        ],
        "prerequisites": ["Basic cybersecurity awareness and backend development experience"],
        "target_audience": [
            "Security Engineers auditing LLM applications",
            "Software Architects designing secure enterprise AI services"
        ],
        "tools_used": ["Python", "OWASP LLM Top 10", "Pydantic", "FastAPI", "Bandit"],
        "estimated_effort": "4 hours total (2 hrs/week over 2 weeks)",
        "curriculum": [
            {
                "title": "Module 1: AI Threat Modeling & Attack Vectors",
                "description": "Understand OWASP LLM top risks including prompt injection and data poisoning.",
                "lessons": [
                    {
                        "title": "OWASP Top 10 for LLM Applications",
                        "duration_minutes": 40,
                        "type": "Deep Dive",
                        "summary": "Analyze real-world exploits involving prompt injection, data leakage, and insecure output."
                    },
                    {
                        "title": "Indirect Prompt Injection in Retrieval Contexts",
                        "duration_minutes": 40,
                        "type": "Lab Session",
                        "summary": "Simulate malicious instruction injection inside indexed documents and craft sanitization wrappers."
                    },
                    {
                        "title": "Privilege Escalation via Unconstrained Tools",
                        "duration_minutes": 40,
                        "type": "Hands-on Exercise",
                        "summary": "Enforce strict scope checking and argument verification on database mutation tools."
                    }
                ]
            },
            {
                "title": "Module 2: Defensive Architecture & Data Protection",
                "description": "Implement input filtering, output sanitization, and PII masking.",
                "lessons": [
                    {
                        "title": "PII Masking & Confidential Data Scrubbing",
                        "duration_minutes": 40,
                        "type": "Code Workshop",
                        "summary": "Build regex and NER-based data redaction middleware for incoming user prompts."
                    },
                    {
                        "title": "Sandboxing Tool Execution Environments",
                        "duration_minutes": 40,
                        "type": "Security Lab",
                        "summary": "Isolate code execution tools inside restricted containers with resource quotas."
                    },
                    {
                        "title": "Security Incident Response for Model Exploits",
                        "duration_minutes": 40,
                        "type": "Scenario Planning",
                        "summary": "Formulate a response runbook for compromised prompts or ungrounded data disclosure."
                    }
                ]
            }
        ],
        "final_project": {
            "title": "Hardened Enterprise Assistant Gateway",
            "description": "Build a security gateway microservice that filters prompt injection attempts, scrubs PII, validates tool parameters, and logs security audit events."
        },
        "instructor_bio": "Elena Torres is a Senior Cybersecurity Researcher specializing in AI product security and defensive application architecture.",
        "faqs": [
            {
                "question": "Does this cover cloud security or model weight stealing?",
                "answer": "The course focuses primarily on application-layer security: inputs, outputs, tool safety, and data privacy."
            }
        ]
    }
}

# General fallback generator for remaining seed courses to ensure 100% complete course content
def get_course_detail(slug: str, title: str, category: str, instructor: str, description: str, short_description: str, tags: list, duration_minutes: int) -> dict:
    if slug in COURSE_DETAILS:
        return COURSE_DETAILS[slug]
    
    # Generate rich, specific content based on course metadata
    mod1_mins = int(duration_minutes * 0.45)
    mod2_mins = duration_minutes - mod1_mins
    effort_hours = round(duration_minutes / 60, 1)
    
    return {
        "what_you_will_learn": [
            f"Master core concepts and practical workflows in {title}",
            f"Apply industry best practices to build production-ready {category} solutions",
            f"Utilize modern tools including {', '.join(tags[:3])} effectively",
            "Diagnose common execution failures, performance bottlenecks, and edge cases",
            "Establish repeatable engineering habits for continuous improvement"
        ],
        "prerequisites": [
            f"Basic familiarity with {category} concepts",
            "A working computer with command-line terminal access"
        ],
        "target_audience": [
            f"Practitioners wanting to build expertise in {title}",
            f"Engineers and Analysts working with {category} tools"
        ],
        "tools_used": [t.title() for t in tags[:4]] + ["Python 3.11", "VS Code"],
        "estimated_effort": f"{effort_hours} hours total ({round(effort_hours/2, 1)} hrs/week over 2 weeks)",
        "curriculum": [
            {
                "title": f"Module 1: Fundamentals of {title}",
                "description": f"Explore core principles, setup, and foundational concepts of {title}.",
                "lessons": [
                    {
                        "title": f"Introduction to {title} Principles",
                        "duration_minutes": max(10, mod1_mins // 3),
                        "type": "Interactive Overview",
                        "summary": f"Deconstruct core building blocks and architecture of {title}."
                    },
                    {
                        "title": f"Core Workflows with {tags[0].title() if tags else 'Tools'}",
                        "duration_minutes": max(15, mod1_mins // 3),
                        "type": "Code Walkthrough",
                        "summary": f"Hands-on demonstration of primary tools and API patterns."
                    },
                    {
                        "title": "Practical Implementation & Configuration",
                        "duration_minutes": max(15, mod1_mins - (mod1_mins // 3) * 2),
                        "type": "Hands-on Exercise",
                        "summary": "Build your first working module with error validation."
                    }
                ]
            },
            {
                "title": f"Module 2: Advanced Patterns & Real-World Application",
                "description": f"Master practical engineering patterns and deploy resilient {category} projects.",
                "lessons": [
                    {
                        "title": "Handling Edge Cases & Error Boundaries",
                        "duration_minutes": max(15, mod2_mins // 3),
                        "type": "Lab Session",
                        "summary": "Implement defensive programming and robust exception management."
                    },
                    {
                        "title": "Performance Optimization & Benchmarking",
                        "duration_minutes": max(15, mod2_mins // 3),
                        "type": "Deep Dive",
                        "summary": "Benchmark performance, identify bottlenecks, and apply efficiency gains."
                    },
                    {
                        "title": "Production Integration & Review",
                        "duration_minutes": max(15, mod2_mins - (mod2_mins // 3) * 2),
                        "type": "Capstone Lab",
                        "summary": "Assemble the final project, run test suites, and review deployment steps."
                    }
                ]
            }
        ],
        "final_project": {
            "title": f"Production {title} Capstone Project",
            "description": f"Build and test a complete, real-world application demonstrating all core skills learned in {title}, featuring comprehensive tests and documentation."
        },
        "instructor_bio": f"{instructor} is a seasoned industry professional with over 8 years of hands-on experience in {category} and technical education.",
        "faqs": [
            {
                "question": f"What background knowledge is required for {title}?",
                "answer": f"A foundational understanding of {category} is helpful, but all key concepts are explained step-by-step."
            },
            {
                "question": "Is source code provided for all exercises?",
                "answer": "Yes! All lessons include repository code samples and step-by-step solution guides."
            }
        ]
    }
