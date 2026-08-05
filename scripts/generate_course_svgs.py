import os

COURSES_DATA = [
    {
        "slug": "autonomous-agent-evaluation-and-red-teaming",
        "title": "Autonomous Agent Evaluation & Red Teaming",
        "category": "Agentic AI",
        "tagline": "Adversarial Testing & Safety Audits",
        "category_color": "#00f2fe",
        "bg_start": "#141e30", "bg_end": "#243b55",
        "glow_1": "#4facfe", "glow_2": "#00f2fe",
        "graphic": """
            <circle cx="180" cy="120" r="45" fill="none" stroke="#ef4444" stroke-width="3" stroke-dasharray="6,4"/>
            <circle cx="180" cy="120" r="25" fill="#ef4444" fill-opacity="0.2" stroke="#ef4444" stroke-width="2"/>
            <line x1="180" y1="65" x2="180" y2="175" stroke="#ef4444" stroke-width="2"/>
            <line x1="125" y1="120" x2="235" y2="120" stroke="#ef4444" stroke-width="2"/>
            <path d="M 220,70 L 260,110 L 220,150" fill="none" stroke="#00f2fe" stroke-width="4" stroke-linecap="round"/>
            <circle cx="260" cy="110" r="12" fill="#00f2fe"/>
        """
    },
    {
        "slug": "memory-architectures-for-long-context-agents",
        "title": "Memory Architectures for Long-Context Agents",
        "category": "Agentic AI",
        "tagline": "Episodic & Vector Context Retention",
        "category_color": "#00f2fe",
        "bg_start": "#141e30", "bg_end": "#243b55",
        "glow_1": "#4facfe", "glow_2": "#00f2fe",
        "graphic": """
            <rect x="120" y="60" width="160" height="35" rx="8" fill="#4facfe" fill-opacity="0.25" stroke="#00f2fe" stroke-width="2"/>
            <text x="135" y="82" font-family="Inter, sans-serif" font-size="12" font-weight="700" fill="#00f2fe">WORKING MEMORY</text>
            <rect x="120" y="110" width="160" height="35" rx="8" fill="#4facfe" fill-opacity="0.2" stroke="#38bdf8" stroke-width="2"/>
            <text x="135" y="132" font-family="Inter, sans-serif" font-size="12" font-weight="700" fill="#38bdf8">EPISODIC BUFFER</text>
            <rect x="120" y="160" width="160" height="35" rx="8" fill="#4facfe" fill-opacity="0.15" stroke="#818cf8" stroke-width="2"/>
            <text x="135" y="182" font-family="Inter, sans-serif" font-size="12" font-weight="700" fill="#818cf8">VECTOR STORE</text>
            <path d="M 290,77 C 320,77 320,177 290,177" fill="none" stroke="#00f2fe" stroke-width="3" stroke-dasharray="4,4"/>
        """
    },
    {
        "slug": "tool-execution-and-api-synthesizers",
        "title": "Tool Execution & API Synthesizers",
        "category": "Agentic AI",
        "tagline": "Sandboxed Execution & Schema Synthesis",
        "category_color": "#00f2fe",
        "bg_start": "#141e30", "bg_end": "#243b55",
        "glow_1": "#4facfe", "glow_2": "#00f2fe",
        "graphic": """
            <rect x="130" y="70" width="140" height="100" rx="14" fill="#0f172a" stroke="#00f2fe" stroke-width="2"/>
            <text x="145" y="98" font-family="monospace" font-size="13" fill="#38bdf8">&gt; exec(tool)</text>
            <text x="145" y="122" font-family="monospace" font-size="11" fill="#10b981">status: 200 OK</text>
            <text x="145" y="146" font-family="monospace" font-size="11" fill="#f59e0b">payload: json</text>
            <circle cx="100" cy="120" r="22" fill="#00f2fe" fill-opacity="0.3" stroke="#00f2fe" stroke-width="2"/>
            <path d="M 90,120 L 110,120 M 100,110 L 100,130" stroke="#00f2fe" stroke-width="3"/>
        """
    },
    {
        "slug": "fine-tuning-open-source-llms",
        "title": "Fine-Tuning Open Source LLMs",
        "category": "Artificial Intelligence",
        "tagline": "PEFT, LoRA & Model Alignment",
        "category_color": "#c084fc",
        "bg_start": "#1a103c", "bg_end": "#2b1b54",
        "glow_1": "#8a2be2", "glow_2": "#c084fc",
        "graphic": """
            <g transform="translate(110, 50)">
                <rect x="0" y="0" width="60" height="140" rx="10" fill="#8a2be2" fill-opacity="0.3" stroke="#c084fc" stroke-width="2"/>
                <text x="12" y="75" font-family="Inter, sans-serif" font-size="12" font-weight="800" fill="#c084fc">BASE</text>
                <text x="75" y="75" font-family="Inter, sans-serif" font-size="20" font-weight="900" fill="#ffffff">+</text>
                <rect x="100" y="20" width="35" height="100" rx="8" fill="#ec4899" fill-opacity="0.4" stroke="#f43f5e" stroke-width="2"/>
                <text x="107" y="75" font-family="Inter, sans-serif" font-size="11" font-weight="800" fill="#f43f5e">LoRA</text>
                <text x="150" y="75" font-family="Inter, sans-serif" font-size="20" font-weight="900" fill="#ffffff">=</text>
                <rect x="175" y="0" width="60" height="140" rx="10" fill="#10b981" fill-opacity="0.3" stroke="#34d399" stroke-width="2"/>
                <text x="183" y="75" font-family="Inter, sans-serif" font-size="12" font-weight="800" fill="#34d399">TUNED</text>
            </g>
        """
    },
    {
        "slug": "multimodal-ai-system-engineering",
        "title": "Multimodal AI System Engineering",
        "category": "Artificial Intelligence",
        "tagline": "Vision, Speech & Audio Fusion",
        "category_color": "#c084fc",
        "bg_start": "#1a103c", "bg_end": "#2b1b54",
        "glow_1": "#8a2be2", "glow_2": "#c084fc",
        "graphic": """
            <circle cx="130" cy="80" r="22" fill="#38bdf8" fill-opacity="0.25" stroke="#38bdf8" stroke-width="2"/>
            <text x="120" y="85" font-family="Inter, sans-serif" font-size="14" fill="#38bdf8">👁️</text>
            <circle cx="130" cy="160" r="22" fill="#ec4899" fill-opacity="0.25" stroke="#ec4899" stroke-width="2"/>
            <text x="120" y="165" font-family="Inter, sans-serif" font-size="14" fill="#ec4899">🎙️</text>
            <path d="M 155,80 L 210,120 M 155,160 L 210,120" stroke="#c084fc" stroke-width="3"/>
            <circle cx="235" cy="120" r="30" fill="#8a2be2" fill-opacity="0.4" stroke="#c084fc" stroke-width="3"/>
            <text x="215" y="125" font-family="Inter, sans-serif" font-size="12" font-weight="800" fill="#ffffff">FUSION</text>
        """
    },
    {
        "slug": "small-language-models-in-edge-production",
        "title": "Small Language Models in Edge Production",
        "category": "Artificial Intelligence",
        "tagline": "Quantization & On-Device Runtimes",
        "category_color": "#c084fc",
        "bg_start": "#1a103c", "bg_end": "#2b1b54",
        "glow_1": "#8a2be2", "glow_2": "#c084fc",
        "graphic": """
            <rect x="130" y="60" width="120" height="120" rx="16" fill="#0f172a" stroke="#c084fc" stroke-width="2"/>
            <rect x="155" y="85" width="70" height="70" rx="8" fill="#8a2be2" fill-opacity="0.3" stroke="#a855f7" stroke-width="2"/>
            <text x="165" y="125" font-family="Inter, sans-serif" font-size="13" font-weight="900" fill="#c084fc">SLM-4B</text>
            <line x1="130" y1="90" x2="110" y2="90" stroke="#c084fc" stroke-width="3"/>
            <line x1="130" y1="120" x2="110" y2="120" stroke="#c084fc" stroke-width="3"/>
            <line x1="130" y1="150" x2="110" y2="150" stroke="#c084fc" stroke-width="3"/>
            <line x1="250" y1="90" x2="270" y2="90" stroke="#c084fc" stroke-width="3"/>
            <line x1="250" y1="120" x2="270" y2="120" stroke="#c084fc" stroke-width="3"/>
            <line x1="250" y1="150" x2="270" y2="150" stroke="#c084fc" stroke-width="3"/>
        """
    },
    {
        "slug": "mlops-model-monitoring-and-drift-detection",
        "title": "MLOps Model Monitoring & Drift Detection",
        "category": "Machine Learning",
        "tagline": "Feature Shift & Performance Tracking",
        "category_color": "#a855f7",
        "bg_start": "#0f172a", "bg_end": "#1e1b4b",
        "glow_1": "#6366f1", "glow_2": "#a855f7",
        "graphic": """
            <path d="M 100,160 Q 150,40 200,160" fill="none" stroke="#6366f1" stroke-width="3"/>
            <path d="M 140,160 Q 190,40 240,160" fill="none" stroke="#ef4444" stroke-width="3" stroke-dasharray="5,5"/>
            <line x1="175" y1="60" x2="215" y2="60" stroke="#ef4444" stroke-width="2"/>
            <polygon points="215,55 225,60 215,65" fill="#ef4444"/>
            <text x="145" y="185" font-family="Inter, sans-serif" font-size="11" font-weight="700" fill="#ef4444">DRIFT DETECTED</text>
        """
    },
    {
        "slug": "graph-neural-networks-in-practice",
        "title": "Graph Neural Networks in Practice",
        "category": "Machine Learning",
        "tagline": "PyTorch Geometric & Node Embeddings",
        "category_color": "#a855f7",
        "bg_start": "#0f172a", "bg_end": "#1e1b4b",
        "glow_1": "#6366f1", "glow_2": "#a855f7",
        "graphic": """
            <line x1="140" y1="80" x2="220" y2="60" stroke="#a855f7" stroke-width="3"/>
            <line x1="140" y1="80" x2="170" y2="160" stroke="#a855f7" stroke-width="3"/>
            <line x1="220" y1="60" x2="250" y2="140" stroke="#a855f7" stroke-width="3"/>
            <line x1="170" y1="160" x2="250" y2="140" stroke="#a855f7" stroke-width="3"/>
            <circle cx="140" cy="80" r="16" fill="#a855f7"/>
            <circle cx="220" cy="60" r="16" fill="#6366f1"/>
            <circle cx="170" cy="160" r="16" fill="#38bdf8"/>
            <circle cx="250" cy="140" r="16" fill="#ec4899"/>
        """
    },
    {
        "slug": "explainable-ai-and-interpretable-models",
        "title": "Explainable AI & Interpretable Models",
        "category": "Machine Learning",
        "tagline": "SHAP, LIME & Feature Attribution",
        "category_color": "#a855f7",
        "bg_start": "#0f172a", "bg_end": "#1e1b4b",
        "glow_1": "#6366f1", "glow_2": "#a855f7",
        "graphic": """
            <rect x="120" y="60" width="130" height="20" rx="4" fill="#38bdf8" fill-opacity="0.8"/>
            <rect x="120" y="90" width="90" height="20" rx="4" fill="#6366f1" fill-opacity="0.8"/>
            <rect x="120" y="120" width="160" height="20" rx="4" fill="#a855f7" fill-opacity="0.8"/>
            <rect x="120" y="150" width="60" height="20" rx="4" fill="#ec4899" fill-opacity="0.8"/>
            <circle cx="240" cy="150" r="28" fill="none" stroke="#ffffff" stroke-width="3"/>
            <line x1="260" y1="170" x2="285" y2="195" stroke="#ffffff" stroke-width="4" stroke-linecap="round"/>
        """
    },
    {
        "slug": "real-time-streaming-analytics-with-apache-flink",
        "title": "Real-Time Streaming Analytics with Apache Flink",
        "category": "Data Science",
        "tagline": "Stateful Stream & Event Processing",
        "category_color": "#0072ff",
        "bg_start": "#091e3a", "bg_end": "#2f80ed",
        "glow_1": "#00c6ff", "glow_2": "#0072ff",
        "graphic": """
            <path d="M 90,120 C 130,50 170,190 210,120 C 250,50 290,190 330,120" fill="none" stroke="#00c6ff" stroke-width="4"/>
            <circle cx="150" cy="85" r="8" fill="#ffffff"/>
            <circle cx="210" cy="120" r="8" fill="#ffffff"/>
            <circle cx="270" cy="155" r="8" fill="#ffffff"/>
            <rect x="170" y="150" width="80" height="30" rx="6" fill="#0072ff" fill-opacity="0.4" stroke="#00c6ff" stroke-width="1.5"/>
            <text x="182" y="170" font-family="Inter, sans-serif" font-size="11" font-weight="800" fill="#ffffff">FLINK</text>
        """
    },
    {
        "slug": "polars-for-high-performance-data-processing",
        "title": "Polars for High-Performance Data Processing",
        "category": "Data Science",
        "tagline": "Lightning-Fast Rust DataFrames",
        "category_color": "#0072ff",
        "bg_start": "#091e3a", "bg_end": "#2f80ed",
        "glow_1": "#00c6ff", "glow_2": "#0072ff",
        "graphic": """
            <polygon points="120,60 260,60 230,110 90,110" fill="#00c6ff" fill-opacity="0.3" stroke="#00c6ff" stroke-width="2"/>
            <polygon points="140,120 280,120 250,170 110,170" fill="#38bdf8" fill-opacity="0.3" stroke="#38bdf8" stroke-width="2"/>
            <path d="M 240,80 L 285,115 L 260,115 L 260,165" fill="none" stroke="#f59e0b" stroke-width="4" stroke-linejoin="round"/>
        """
    },
    {
        "slug": "causal-inference-for-data-science",
        "title": "Causal Inference for Data Science",
        "category": "Data Science",
        "tagline": "DoWhy, Counterfactuals & DAGs",
        "category_color": "#0072ff",
        "bg_start": "#091e3a", "bg_end": "#2f80ed",
        "glow_1": "#00c6ff", "glow_2": "#0072ff",
        "graphic": """
            <circle cx="140" cy="150" r="22" fill="#00c6ff" fill-opacity="0.3" stroke="#00c6ff" stroke-width="2"/>
            <text x="133" y="156" font-family="Inter, sans-serif" font-size="16" font-weight="900" fill="#ffffff">T</text>
            <circle cx="260" cy="150" r="22" fill="#10b981" fill-opacity="0.3" stroke="#10b981" stroke-width="2"/>
            <text x="253" y="156" font-family="Inter, sans-serif" font-size="16" font-weight="900" fill="#ffffff">Y</text>
            <circle cx="200" cy="70" r="22" fill="#f59e0b" fill-opacity="0.3" stroke="#f59e0b" stroke-width="2"/>
            <text x="193" y="76" font-family="Inter, sans-serif" font-size="16" font-weight="900" fill="#ffffff">Z</text>
            <line x1="162" y1="150" x2="238" y2="150" stroke="#00c6ff" stroke-width="3"/>
            <line x1="185" y1="88" x2="150" y2="130" stroke="#f59e0b" stroke-width="2"/>
            <line x1="215" y1="88" x2="250" y2="130" stroke="#f59e0b" stroke-width="2"/>
        """
    },
    {
        "slug": "python-concurrency-asyncio-and-multiprocessing",
        "title": "Python Concurrency: Asyncio & Multiprocessing",
        "category": "Python",
        "tagline": "Event Loops, Threads & CPU Pools",
        "category_color": "#38bdf8",
        "bg_start": "#1e293b", "bg_end": "#0f172a",
        "glow_1": "#38bdf8", "glow_2": "#f59e0b",
        "graphic": """
            <circle cx="190" cy="120" r="50" fill="none" stroke="#38bdf8" stroke-width="4" stroke-dasharray="15,8"/>
            <circle cx="190" cy="120" r="18" fill="#f59e0b"/>
            <line x1="190" y1="40" x2="190" y2="70" stroke="#38bdf8" stroke-width="3"/>
            <line x1="190" y1="170" x2="190" y2="200" stroke="#38bdf8" stroke-width="3"/>
            <line x1="110" y1="120" x2="140" y2="120" stroke="#38bdf8" stroke-width="3"/>
            <line x1="240" y1="120" x2="270" y2="120" stroke="#38bdf8" stroke-width="3"/>
        """
    },
    {
        "slug": "design-patterns-in-modern-python",
        "title": "Design Patterns in Modern Python",
        "category": "Python",
        "tagline": "Clean Code, Protocols & Factories",
        "category_color": "#38bdf8",
        "bg_start": "#1e293b", "bg_end": "#0f172a",
        "glow_1": "#38bdf8", "glow_2": "#f59e0b",
        "graphic": """
            <rect x="110" y="60" width="70" height="70" rx="12" fill="#38bdf8" fill-opacity="0.3" stroke="#38bdf8" stroke-width="2"/>
            <rect x="195" y="60" width="70" height="70" rx="12" fill="#f59e0b" fill-opacity="0.3" stroke="#f59e0b" stroke-width="2"/>
            <rect x="150" y="130" width="70" height="70" rx="12" fill="#10b981" fill-opacity="0.3" stroke="#10b981" stroke-width="2"/>
            <path d="M 145,130 L 180,95 L 215,130" fill="none" stroke="#ffffff" stroke-width="2" stroke-dasharray="3,3"/>
        """
    },
    {
        "slug": "nextjs-fullstack-architecture",
        "title": "Next.js Fullstack Architecture",
        "category": "Web Development",
        "tagline": "React Server Components & App Router",
        "category_color": "#3b82f6",
        "bg_start": "#0f172a", "bg_end": "#1e293b",
        "glow_1": "#06b6d4", "glow_2": "#3b82f6",
        "graphic": """
            <rect x="120" y="60" width="150" height="110" rx="14" fill="#020617" stroke="#3b82f6" stroke-width="2"/>
            <path d="M 150,140 L 210,80 L 210,140" fill="none" stroke="#ffffff" stroke-width="4" stroke-linecap="round"/>
            <circle cx="210" cy="80" r="6" fill="#06b6d4"/>
            <text x="140" y="160" font-family="Inter, sans-serif" font-size="11" font-weight="800" fill="#38bdf8">SERVER / CLIENT</text>
        """
    },
    {
        "slug": "web-performance-optimization-masterclass",
        "title": "Web Performance Optimization Masterclass",
        "category": "Web Development",
        "tagline": "Core Web Vitals & Sub-Second Loading",
        "category_color": "#3b82f6",
        "bg_start": "#0f172a", "bg_end": "#1e293b",
        "glow_1": "#06b6d4", "glow_2": "#3b82f6",
        "graphic": """
            <path d="M 120,160 A 70,70 0 0 1 260,160" fill="none" stroke="#1e293b" stroke-width="12"/>
            <path d="M 120,160 A 70,70 0 0 1 245,110" fill="none" stroke="#10b981" stroke-width="12" stroke-linecap="round"/>
            <line x1="190" y1="160" x2="235" y2="120" stroke="#ffffff" stroke-width="4" stroke-linecap="round"/>
            <circle cx="190" cy="160" r="8" fill="#ffffff"/>
            <text x="165" y="190" font-family="Inter, sans-serif" font-size="12" font-weight="900" fill="#10b981">99 / 100</text>
        """
    },
    {
        "slug": "building-real-time-web-apps-with-websockets",
        "title": "Building Real-Time Web Apps with WebSockets",
        "category": "Web Development",
        "tagline": "Bi-Directional Event Streams",
        "category_color": "#3b82f6",
        "bg_start": "#0f172a", "bg_end": "#1e293b",
        "glow_1": "#06b6d4", "glow_2": "#3b82f6",
        "graphic": """
            <rect x="100" y="80" width="70" height="80" rx="8" fill="#1e293b" stroke="#3b82f6" stroke-width="2"/>
            <rect x="230" y="80" width="70" height="80" rx="8" fill="#1e293b" stroke="#06b6d4" stroke-width="2"/>
            <path d="M 175,105 L 225,105" fill="none" stroke="#10b981" stroke-width="3"/>
            <polygon points="220,100 230,105 220,110" fill="#10b981"/>
            <path d="M 225,135 L 175,135" fill="none" stroke="#38bdf8" stroke-width="3"/>
            <polygon points="180,130 170,135 180,140" fill="#38bdf8"/>
        """
    },
    {
        "slug": "terraform-infrastructure-as-code",
        "title": "Terraform Infrastructure as Code",
        "category": "Cloud Computing",
        "tagline": "Declarative Multi-Cloud Provisioning",
        "category_color": "#60a5fa",
        "bg_start": "#0d1f2d", "bg_end": "#1d3557",
        "glow_1": "#38bdf8", "glow_2": "#60a5fa",
        "graphic": """
            <polygon points="140,70 190,40 190,100 140,130" fill="#5c4ee5"/>
            <polygon points="195,40 245,70 195,100" fill="#5c4ee5" fill-opacity="0.7"/>
            <polygon points="195,105 245,135 195,165 145,135" fill="#5c4ee5"/>
        """
    },
    {
        "slug": "serverless-architectures-on-aws",
        "title": "Serverless Architectures on AWS",
        "category": "Cloud Computing",
        "tagline": "EventBridge, Lambda & DynamoDB",
        "category_color": "#60a5fa",
        "bg_start": "#0d1f2d", "bg_end": "#1d3557",
        "glow_1": "#38bdf8", "glow_2": "#60a5fa",
        "graphic": """
            <path d="M 190,50 L 140,120 L 180,120 L 160,190 L 230,110 L 190,110 Z" fill="#f59e0b" stroke="#ffffff" stroke-width="1.5"/>
        """
    },
    {
        "slug": "cloud-security-posture-management",
        "title": "Cloud Security Posture Management",
        "category": "Cybersecurity",
        "tagline": "CSPM, IAM & Policy Enforcements",
        "category_color": "#f43f5e",
        "bg_start": "#1a0f1a", "bg_end": "#2d122d",
        "glow_1": "#ec4899", "glow_2": "#f43f5e",
        "graphic": """
            <path d="M 120,100 Q 120,60 190,60 Q 260,60 260,100 C 260,160 190,190 190,190 C 190,190 120,160 120,100 Z" fill="#ec4899" fill-opacity="0.2" stroke="#f43f5e" stroke-width="3"/>
            <path d="M 165,115 L 182,132 L 215,95" fill="none" stroke="#10b981" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
        """
    },
    {
        "slug": "zero-trust-network-architecture",
        "title": "Zero Trust Network Architecture",
        "category": "Cybersecurity",
        "tagline": "Microsegmentation & Identity Proxies",
        "category_color": "#f43f5e",
        "bg_start": "#1a0f1a", "bg_end": "#2d122d",
        "glow_1": "#ec4899", "glow_2": "#f43f5e",
        "graphic": """
            <rect x="130" y="95" width="120" height="85" rx="10" fill="#1e293b" stroke="#f43f5e" stroke-width="3"/>
            <path d="M 160,95 L 160,75 A 30,30 0 0 1 220,75 L 220,95" fill="none" stroke="#f43f5e" stroke-width="3"/>
            <circle cx="190" cy="130" r="10" fill="#f43f5e"/>
            <line x1="190" y1="140" x2="190" y2="155" stroke="#f43f5e" stroke-width="3"/>
        """
    },
    {
        "slug": "ai-product-roadmap-strategy",
        "title": "AI Product Roadmap Strategy",
        "category": "Product Management",
        "tagline": "Feasibility, ROI & Product Milestones",
        "category_color": "#fbbf24",
        "bg_start": "#2d1212", "bg_end": "#1c1010",
        "glow_1": "#f97316", "glow_2": "#fbbf24",
        "graphic": """
            <line x1="100" y1="160" x2="280" y2="70" stroke="#f97316" stroke-width="4"/>
            <circle cx="130" cy="145" r="14" fill="#fbbf24"/>
            <circle cx="190" cy="115" r="14" fill="#fbbf24"/>
            <circle cx="250" cy="85" r="14" fill="#10b981"/>
            <text x="245" y="90" font-family="Inter, sans-serif" font-size="12" font-weight="900" fill="#000000">★</text>
        """
    },
    {
        "slug": "growth-product-management-essentials",
        "title": "Growth Product Management Essentials",
        "category": "Product Management",
        "tagline": "Funnel Optimization & Retention",
        "category_color": "#fbbf24",
        "bg_start": "#2d1212", "bg_end": "#1c1010",
        "glow_1": "#f97316", "glow_2": "#fbbf24",
        "graphic": """
            <polygon points="100,60 280,60 230,120 150,120" fill="#f97316" fill-opacity="0.3" stroke="#f97316" stroke-width="2"/>
            <polygon points="150,125 230,125 205,175 175,175" fill="#fbbf24" fill-opacity="0.5" stroke="#fbbf24" stroke-width="2"/>
            <path d="M 240,130 C 270,130 270,170 240,170" fill="none" stroke="#10b981" stroke-width="3" stroke-dasharray="4,3"/>
        """
    },
    {
        "slug": "advanced-motion-design-for-web-interfaces",
        "title": "Advanced Motion Design for Web Interfaces",
        "category": "UI/UX Design",
        "tagline": "Micro-Interactions & Spring Physics",
        "category_color": "#d9f1df",
        "bg_start": "#1e3c2b", "bg_end": "#17221d",
        "glow_1": "#246b4a", "glow_2": "#d9f1df",
        "graphic": """
            <path d="M 100,160 C 140,60 200,200 280,70" fill="none" stroke="#d9f1df" stroke-width="4"/>
            <circle cx="140" cy="120" r="10" fill="#246b4a" stroke="#d9f1df" stroke-width="2"/>
            <circle cx="210" cy="150" r="16" fill="#d9f1df"/>
        """
    },
    {
        "slug": "design-systems-for-enterprise-apps",
        "title": "Design Systems for Enterprise Apps",
        "category": "UI/UX Design",
        "tagline": "Token Systems & Component Libraries",
        "category_color": "#d9f1df",
        "bg_start": "#1e3c2b", "bg_end": "#17221d",
        "glow_1": "#246b4a", "glow_2": "#d9f1df",
        "graphic": """
            <rect x="110" y="60" width="60" height="40" rx="8" fill="#d9f1df" fill-opacity="0.3" stroke="#d9f1df" stroke-width="2"/>
            <rect x="180" y="60" width="60" height="40" rx="8" fill="#38bdf8" fill-opacity="0.3" stroke="#38bdf8" stroke-width="2"/>
            <rect x="110" y="110" width="130" height="50" rx="8" fill="#246b4a" fill-opacity="0.4" stroke="#d9f1df" stroke-width="2"/>
        """
    },
    {
        "slug": "executive-financial-modeling-and-analysis",
        "title": "Executive Financial Modeling & Analysis",
        "category": "Business Analytics",
        "tagline": "3-Statement Models & Unit Economics",
        "category_color": "#ec4899",
        "bg_start": "#1e1b4b", "bg_end": "#31103f",
        "glow_1": "#a855f7", "glow_2": "#ec4899",
        "graphic": """
            <rect x="110" y="130" width="30" height="50" fill="#a855f7" rx="4"/>
            <rect x="150" y="100" width="30" height="80" fill="#ec4899" rx="4"/>
            <rect x="190" y="70" width="30" height="110" fill="#34d399" rx="4"/>
            <path d="M 125,120 L 165,90 L 205,55 L 245,40" fill="none" stroke="#ffffff" stroke-width="3"/>
        """
    },
    {
        "slug": "cohort-analysis-and-customer-lifetime-value",
        "title": "Cohort Analysis & Customer Lifetime Value",
        "category": "Business Analytics",
        "tagline": "Retention Heatmaps & LTV Payback",
        "category_color": "#ec4899",
        "bg_start": "#1e1b4b", "bg_end": "#31103f",
        "glow_1": "#a855f7", "glow_2": "#ec4899",
        "graphic": """
            <rect x="110" y="60" width="40" height="30" fill="#ec4899" fill-opacity="0.9" rx="4"/>
            <rect x="155" y="60" width="40" height="30" fill="#ec4899" fill-opacity="0.6" rx="4"/>
            <rect x="200" y="60" width="40" height="30" fill="#ec4899" fill-opacity="0.3" rx="4"/>
            <rect x="110" y="95" width="40" height="30" fill="#a855f7" fill-opacity="0.9" rx="4"/>
            <rect x="155" y="95" width="40" height="30" fill="#a855f7" fill-opacity="0.6" rx="4"/>
            <rect x="110" y="130" width="40" height="30" fill="#3b82f6" fill-opacity="0.9" rx="4"/>
        """
    },
    {
        "slug": "gitops-pipelines-with-argocd-and-flux",
        "title": "GitOps Pipelines with ArgoCD & Flux",
        "category": "DevOps",
        "tagline": "Declarative Continuous Deployment",
        "category_color": "#10b981",
        "bg_start": "#0f172a", "bg_end": "#172554",
        "glow_1": "#3b82f6", "glow_2": "#10b981",
        "graphic": """
            <circle cx="130" cy="120" r="18" fill="#10b981" fill-opacity="0.3" stroke="#10b981" stroke-width="2"/>
            <text x="122" y="125" font-family="Inter, sans-serif" font-size="12" font-weight="900" fill="#10b981">GIT</text>
            <path d="M 150,120 L 220,120" stroke="#3b82f6" stroke-width="3" stroke-dasharray="4,4"/>
            <circle cx="240" cy="120" r="22" fill="#3b82f6" fill-opacity="0.3" stroke="#3b82f6" stroke-width="2"/>
            <text x="228" y="125" font-family="Inter, sans-serif" font-size="11" font-weight="900" fill="#3b82f6">K8S</text>
        """
    },
    {
        "slug": "site-reliability-engineering-practices",
        "title": "Site Reliability Engineering Practices",
        "category": "DevOps",
        "tagline": "SLOs, Error Budgets & Incident Response",
        "category_color": "#10b981",
        "bg_start": "#0f172a", "bg_end": "#172554",
        "glow_1": "#3b82f6", "glow_2": "#10b981",
        "graphic": """
            <circle cx="190" cy="120" r="55" fill="none" stroke="#1e293b" stroke-width="10"/>
            <path d="M 135,120 A 55,55 0 1 1 245,120" fill="none" stroke="#10b981" stroke-width="10"/>
            <text x="160" y="125" font-family="Inter, sans-serif" font-size="14" font-weight="900" fill="#ffffff">99.99%</text>
        """
    },
    {
        "slug": "cloud-cost-optimization-and-finops",
        "title": "Cloud Cost Optimization & FinOps",
        "category": "Cloud Computing",
        "tagline": "Cloud Cost Allocation & Right-Sizing",
        "category_color": "#60a5fa",
        "bg_start": "#0d1f2d", "bg_end": "#1d3557",
        "glow_1": "#38bdf8", "glow_2": "#60a5fa",
        "graphic": """
            <path d="M 120,70 Q 140,50 180,60 Q 220,40 250,70 Q 270,90 250,110 L 120,110 Z" fill="#60a5fa" fill-opacity="0.2" stroke="#60a5fa" stroke-width="2"/>
            <circle cx="185" cy="155" r="28" fill="#10b981"/>
            <text x="177" y="164" font-family="Inter, sans-serif" font-size="24" font-weight="900" fill="#ffffff">$</text>
        """
    }
]

import html

def format_title(title):
    escaped_title = html.escape(title)
    words = escaped_title.split()
    if len(words) <= 4:
        return f'<text x="0" y="75" font-family="Inter, system-ui, sans-serif" font-size="26" font-weight="900" fill="#ffffff" letter-spacing="-0.5">{escaped_title}</text>'
    
    mid = len(words) // 2
    line1 = " ".join(words[:mid])
    line2 = " ".join(words[mid:])
    return f'''<text x="0" y="70" font-family="Inter, system-ui, sans-serif" font-size="25" font-weight="900" fill="#ffffff" letter-spacing="-0.5">{line1}</text>
    <text x="0" y="105" font-family="Inter, system-ui, sans-serif" font-size="25" font-weight="900" fill="#ffffff" letter-spacing="-0.5">{line2}</text>'''

out_dir = "/home/arch/DEV/SmartReco/app/static/images/courses"
os.makedirs(out_dir, exist_ok=True)

for item in COURSES_DATA:
    slug = item["slug"]
    title_xml = format_title(item["title"])
    category_upper = html.escape(item["category"].upper())
    tagline_xml = html.escape(item["tagline"])
    pill_width = max(110, len(category_upper) * 11)
    
    svg_content = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 450" width="100%" height="100%">
  <defs>
    <linearGradient id="bgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{item['bg_start']}"/>
      <stop offset="100%" stop-color="{item['bg_end']}"/>
    </linearGradient>
    <linearGradient id="cardGrad" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#ffffff" stop-opacity="0.15"/>
      <stop offset="100%" stop-color="#ffffff" stop-opacity="0.03"/>
    </linearGradient>
    <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="15" result="blur"/>
      <feComposite in="SourceGraphic" in2="blur" operator="over"/>
    </filter>
  </defs>

  <!-- Background -->
  <rect width="800" height="450" fill="url(#bgGrad)"/>
  
  <!-- Grid Lines -->
  <g stroke="#ffffff" stroke-opacity="0.05" stroke-width="1">
    <line x1="0" y1="90" x2="800" y2="90"/>
    <line x1="0" y1="180" x2="800" y2="180"/>
    <line x1="0" y1="270" x2="800" y2="270"/>
    <line x1="0" y1="360" x2="800" y2="360"/>
    <line x1="200" y1="0" x2="200" y2="450"/>
    <line x1="400" y1="0" x2="400" y2="450"/>
    <line x1="600" y1="0" x2="600" y2="450"/>
  </g>

  <!-- Glowing Orbs -->
  <circle cx="650" cy="120" r="180" fill="{item['glow_1']}" opacity="0.25" filter="url(#glow)"/>
  <circle cx="150" cy="380" r="140" fill="{item['glow_2']}" opacity="0.15" filter="url(#glow)"/>

  <!-- Visual Graphic Box -->
  <g transform="translate(380, 40)">
    <rect x="0" y="0" width="360" height="240" rx="20" fill="url(#cardGrad)" stroke="#ffffff" stroke-opacity="0.2" stroke-width="1.5"/>
    <g transform="translate(-20, 0)">
      {item['graphic']}
    </g>
  </g>

  <!-- Content Glass Panel -->
  <rect x="50" y="50" width="480" height="350" rx="24" fill="#0d1512" fill-opacity="0.65" stroke="#ffffff" stroke-opacity="0.15" stroke-width="1.5"/>

  <!-- Text Content -->
  <g transform="translate(85, 95)">
    <!-- Category Pill -->
    <rect x="0" y="0" width="{pill_width}" height="28" rx="14" fill="{item['glow_1']}" fill-opacity="0.3" stroke="{item['category_color']}" stroke-opacity="0.6" stroke-width="1"/>
    <text x="12" y="18" font-family="Inter, system-ui, sans-serif" font-size="11" font-weight="800" fill="{item['category_color']}" letter-spacing="1.5">{category_upper}</text>

    <!-- Title -->
    {title_xml}

    <!-- Tagline -->
    <text x="0" y="155" font-family="Inter, system-ui, sans-serif" font-size="14" font-weight="600" fill="#a0aec0">
      {tagline_xml}
    </text>

    <!-- Badges -->
    <g transform="translate(0, 195)">
      <rect x="0" y="0" width="110" height="32" rx="8" fill="#ffffff" fill-opacity="0.08" stroke="#ffffff" stroke-opacity="0.15"/>
      <text x="14" y="21" font-family="Inter, system-ui, sans-serif" font-size="12" font-weight="700" fill="#ffffff">SmartReco</text>

      <rect x="122" y="0" width="140" height="32" rx="8" fill="{item['glow_1']}" fill-opacity="0.25"/>
      <text x="134" y="21" font-family="Inter, system-ui, sans-serif" font-size="12" font-weight="700" fill="{item['category_color']}">★ Verified Course</text>
    </g>
  </g>
</svg>'''

    filepath = os.path.join(out_dir, f"{slug}.svg")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(svg_content)

print(f"Successfully generated {len(COURSES_DATA)} custom SVG course images in {out_dir}")
