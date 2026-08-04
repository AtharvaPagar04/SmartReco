"""
Generates unique, topic-tailored, high-resolution SVG course thumbnail images for all 30 SmartReco courses.
Ensures zero repeated images across the entire catalog.
"""

import sys
from pathlib import Path

sys.path.insert(0, ".")
from scripts.seed_data import SEED_COURSES

OUTPUT_DIR = Path("app/static/images/courses")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 30 unique color palettes and visual concepts for each course
COURSE_VISUAL_STYLES = {
    "introduction-to-agentic-ai": {
        "bg_start": "#0f2027", "bg_end": "#203a43", "accent": "#20b2aa", "highlight": "#00ffcc",
        "icon": "AGENT_LOOP", "subtitle": "Autonomous Reasoning & Control"
    },
    "advanced-langgraph-workflows": {
        "bg_start": "#141e30", "bg_end": "#243b55", "accent": "#4facfe", "highlight": "#00f2fe",
        "icon": "GRAPH_DAG", "subtitle": "Durable State Machines & Graphs"
    },
    "production-rag-systems": {
        "bg_start": "#0b8793", "bg_end": "#360033", "accent": "#00c6ff", "highlight": "#f857a6",
        "icon": "VECTOR_SEARCH", "subtitle": "Hybrid Indexing & Grounding"
    },
    "multi-agent-orchestration": {
        "bg_start": "#1f1c2c", "bg_end": "#928dab", "accent": "#ff007f", "highlight": "#7b2cbf",
        "icon": "AGENT_SWARM", "subtitle": "Supervisor & Peer Networks"
    },
    "python-for-beginners": {
        "bg_start": "#1e3c72", "bg_end": "#2a5298", "accent": "#fbc531", "highlight": "#4cd137",
        "icon": "PYTHON_SNAKE", "subtitle": "Fundamentals to Projects"
    },
    "fastapi-backend-development": {
        "bg_start": "#0575e6", "bg_end": "#021b79", "accent": "#00f2fe", "highlight": "#4facfe",
        "icon": "LIGHTNING_API", "subtitle": "Async OpenAPI & Pydantic"
    },
    "vector-databases-in-practice": {
        "bg_start": "#16222a", "bg_end": "#3a6073", "accent": "#38ef7d", "highlight": "#11998e",
        "icon": "VECTOR_CUBE", "subtitle": "Qdrant & Vector Embeddings"
    },
    "prompt-engineering-fundamentals": {
        "bg_start": "#2b5876", "bg_end": "#4e4376", "accent": "#ff9a9e", "highlight": "#fecfef",
        "icon": "PROMPT_TERMINAL", "subtitle": "Structuring LLM Prompts"
    },
    "ai-application-observability": {
        "bg_start": "#000000", "bg_end": "#434343", "accent": "#f39c12", "highlight": "#e74c3c",
        "icon": "TELEMETRY_GAUGE", "subtitle": "Tracing, Cost & Latency"
    },
    "building-secure-ai-products": {
        "bg_start": "#1a2a6c", "bg_end": "#b21f1f", "accent": "#fdbb2d", "highlight": "#ff5252",
        "icon": "SECURITY_SHIELD", "subtitle": "Guardrails & Data Safety"
    },
    "typescript-for-backend-teams": {
        "bg_start": "#007acc", "bg_end": "#1e3c72", "accent": "#3178c6", "highlight": "#ffffff",
        "icon": "TS_INTERFACE", "subtitle": "Strict Typing & Microservices"
    },
    "async-python-mastery": {
        "bg_start": "#2c3e50", "bg_end": "#3498db", "accent": "#e74c3c", "highlight": "#2ecc71",
        "icon": "EVENT_LOOP", "subtitle": "Asyncio, Tasks & Queues"
    },
    "fullstack-nextjs-fastapi": {
        "bg_start": "#111111", "bg_end": "#2d3748", "accent": "#61dafb", "highlight": "#00f2fe",
        "icon": "FULLSTACK_NODES", "subtitle": "Modern React & Python API"
    },
    "graphql-apis-in-python": {
        "bg_start": "#e10098", "bg_end": "#230b35", "accent": "#ff79c6", "highlight": "#bd93f9",
        "icon": "GRAPHQL_HEX", "subtitle": "Typed Queries & Resolvers"
    },
    "microservice-patterns-in-python": {
        "bg_start": "#200122", "bg_end": "#6f0000", "accent": "#ff4e50", "highlight": "#f9d423",
        "icon": "MICROSERVICES_MESH", "subtitle": "Event-Driven Services"
    },
    "postgresql-for-developers": {
        "bg_start": "#336791", "bg_end": "#1d2b3a", "accent": "#5294e2", "highlight": "#8bb8f1",
        "icon": "POSTGRES_DB", "subtitle": "Indexing & Query Tuning"
    },
    "docker-kubernetes-for-devs": {
        "bg_start": "#326ce5", "bg_end": "#0d1b2a", "accent": "#00d2ff", "highlight": "#3a7bd5",
        "icon": "CONTAINER_PODS", "subtitle": "Containers & Cluster Ops"
    },
    "data-engineering-pipelines": {
        "bg_start": "#134e5e", "bg_end": "#71b280", "accent": "#a8e063", "highlight": "#56ab2f",
        "icon": "ETL_PIPELINE", "subtitle": "Spark, Airflow & Streams"
    },
    "redis-caching-and-queues": {
        "bg_start": "#d31027", "bg_end": "#ea384d", "accent": "#ff8a00", "highlight": "#ffe000",
        "icon": "REDIS_CACHE", "subtitle": "In-Memory Queues & PubSub"
    },
    "system-design-interview-prep": {
        "bg_start": "#0f2027", "bg_end": "#2c5364", "accent": "#00c6ff", "highlight": "#0072ff",
        "icon": "BLUEPRINT_ARCH", "subtitle": "Scalability & Load Balancers"
    },
    "react-for-backend-developers": {
        "bg_start": "#20232a", "bg_end": "#282c34", "accent": "#61dafb", "highlight": "#28a745",
        "icon": "REACT_ATOM", "subtitle": "Component Hooks & State"
    },
    "tailwind-css-mastery": {
        "bg_start": "#0f172a", "bg_end": "#1e293b", "accent": "#38bdf8", "highlight": "#818cf8",
        "icon": "TAILWIND_WAVE", "subtitle": "Utility-First Design"
    },
    "git-github-advanced-workflows": {
        "bg_start": "#24292e", "bg_end": "#f05032", "accent": "#ff7b72", "highlight": "#ffa657",
        "icon": "GIT_BRANCHES", "subtitle": "Rebase, PRs & Merge Strategies"
    },
    "ci-cd-pipelines-with-github-actions": {
        "bg_start": "#161b22", "bg_end": "#208b3a", "accent": "#2ea043", "highlight": "#56d364",
        "icon": "CICD_RUNNER", "subtitle": "Automated Testing & Builds"
    },
    "testing-python-applications": {
        "bg_start": "#1b2a47", "bg_end": "#2e4057", "accent": "#00e676", "highlight": "#69f0ae",
        "icon": "TEST_CHECK", "subtitle": "Pytest, Fixtures & Mocks"
    },
    "llm-finetuning-basics": {
        "bg_start": "#3a1c71", "bg_end": "#d76d77", "accent": "#ffaf7b", "highlight": "#ffffff",
        "icon": "NEURAL_NET", "subtitle": "LoRA, PEFT & Model Tuning"
    },
    "semantic-search-architecture": {
        "bg_start": "#004e92", "bg_end": "#000428", "accent": "#00c6ff", "highlight": "#0072ff",
        "icon": "SEMANTIC_LENS", "subtitle": "Dense Vector & BM25 Hybrid"
    },
    "kubernetes-operators-in-python": {
        "bg_start": "#326ce5", "bg_end": "#112244", "accent": "#4285f4", "highlight": "#34a853",
        "icon": "K8S_OPERATOR", "subtitle": "CRDs & Control Loops"
    },
    "kafka-event-driven-architecture": {
        "bg_start": "#231f20", "bg_end": "#434040", "accent": "#00f2fe", "highlight": "#4facfe",
        "icon": "KAFKA_STREAM", "subtitle": "Topics, Partitions & Streams"
    },
    "responsible-ai-product-strategy": {
        "bg_start": "#2c3e50", "bg_end": "#4ca1af", "accent": "#c4e538", "highlight": "#12cbd4",
        "icon": "ETHICS_RADAR", "subtitle": "Risk, Governance & Audits"
    }
}

def generate_svg_icon(icon_type: str, color: str) -> str:
    if icon_type == "AGENT_LOOP":
        return f'<circle cx="200" cy="120" r="45" fill="none" stroke="{color}" stroke-width="6" stroke-dasharray="10 6"/><polygon points="230,85 245,100 220,105" fill="{color}"/><circle cx="200" cy="120" r="16" fill="{color}"/>'
    elif icon_type == "GRAPH_DAG":
        return f'<circle cx="150" cy="100" r="16" fill="{color}"/><circle cx="250" cy="80" r="16" fill="{color}"/><circle cx="250" cy="150" r="16" fill="{color}"/><line x1="164" y1="95" x2="236" y2="85" stroke="{color}" stroke-width="4"/><line x1="164" y1="108" x2="236" y2="142" stroke="{color}" stroke-width="4"/>'
    elif icon_type == "VECTOR_SEARCH":
        return f'<rect x="140" y="80" width="120" height="80" rx="10" fill="none" stroke="{color}" stroke-width="5"/><circle cx="180" cy="110" r="8" fill="{color}"/><circle cx="220" cy="130" r="8" fill="{color}"/><line x1="160" y1="140" x2="240" y2="100" stroke="{color}" stroke-width="3" stroke-dasharray="4 4"/>'
    elif icon_type == "AGENT_SWARM":
        return f'<circle cx="160" cy="100" r="18" fill="{color}"/><circle cx="240" cy="100" r="18" fill="{color}"/><circle cx="200" cy="150" r="18" fill="{color}"/><line x1="175" y1="100" x2="225" y2="100" stroke="{color}" stroke-width="4"/><line x1="170" y1="114" x2="190" y2="138" stroke="{color}" stroke-width="4"/><line x1="230" y1="114" x2="210" y2="138" stroke="{color}" stroke-width="4"/>'
    elif icon_type == "PYTHON_SNAKE":
        return f'<path d="M160,110 C160,80 200,80 200,110 C200,140 240,140 240,110" fill="none" stroke="{color}" stroke-width="12" stroke-linecap="round"/><circle cx="240" cy="100" r="4" fill="#000"/>'
    elif icon_type == "LIGHTNING_API":
        return f'<polygon points="210,65 160,125 195,125 180,175 240,110 205,110" fill="{color}"/>'
    elif icon_type == "SECURITY_SHIELD":
        return f'<path d="M200,70 L250,90 C250,140 200,170 200,170 C200,170 150,140 150,90 Z" fill="none" stroke="{color}" stroke-width="6"/><path d="M190,115 L200,125 L220,105" fill="none" stroke="{color}" stroke-width="6" stroke-linecap="round"/>'
    elif icon_type == "POSTGRES_DB":
        return f'<ellipse cx="200" cy="85" rx="55" ry="18" fill="none" stroke="{color}" stroke-width="5"/><path d="M145,85 L145,145 C145,160 255,160 255,145 L255,85" fill="none" stroke="{color}" stroke-width="5"/><ellipse cx="200" cy="115" rx="55" ry="16" fill="none" stroke="{color}" stroke-width="4" stroke-dasharray="6 4"/>'
    elif icon_type == "CONTAINER_PODS":
        return f'<rect x="145" y="80" width="50" height="40" rx="6" fill="none" stroke="{color}" stroke-width="5"/><rect x="205" y="80" width="50" height="40" rx="6" fill="none" stroke="{color}" stroke-width="5"/><rect x="175" y="130" width="50" height="40" rx="6" fill="none" stroke="{color}" stroke-width="5"/>'
    elif icon_type == "REACT_ATOM":
        return f'<ellipse cx="200" cy="120" rx="60" ry="22" fill="none" stroke="{color}" stroke-width="5" transform="rotate(30 200 120)"/><ellipse cx="200" cy="120" rx="60" ry="22" fill="none" stroke="{color}" stroke-width="5" transform="rotate(150 200 120)"/><circle cx="200" cy="120" r="10" fill="{color}"/>'
    elif icon_type == "GIT_BRANCHES":
        return f'<line x1="160" y1="75" x2="160" y2="165" stroke="{color}" stroke-width="6"/><circle cx="160" cy="85" r="12" fill="{color}"/><circle cx="160" cy="155" r="12" fill="{color}"/><circle cx="230" cy="115" r="12" fill="{color}"/><path d="M160,140 C190,140 230,135 230,115" fill="none" stroke="{color}" stroke-width="5"/>'
    else:
        return f'<rect x="150" y="80" width="100" height="80" rx="12" fill="none" stroke="{color}" stroke-width="6"/><circle cx="200" cy="120" r="20" fill="{color}"/>'

def create_course_svg(slug: str, title: str, category: str) -> str:
    style = COURSE_VISUAL_STYLES.get(slug, {
        "bg_start": "#1e3c2b", "bg_end": "#17221d", "accent": "#246b4a", "highlight": "#d9f1df",
        "icon": "GENERIC", "subtitle": f"{category} Masterclass"
    })
    
    icon_svg = generate_svg_icon(style["icon"], style["highlight"])
    safe_title = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    safe_category = category.upper()
    subtitle = style.get("subtitle", f"{category} Specialization").replace("&", "&amp;")

    svg_content = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 450" width="100%" height="100%">
  <defs>
    <linearGradient id="bgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{style['bg_start']}"/>
      <stop offset="100%" stop-color="{style['bg_end']}"/>
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
  
  <!-- Subtle Grid Lines -->
  <g stroke="#ffffff" stroke-opacity="0.05" stroke-width="1">
    <line x1="0" y1="90" x2="800" y2="90"/>
    <line x1="0" y1="180" x2="800" y2="180"/>
    <line x1="0" y1="270" x2="800" y2="270"/>
    <line x1="0" y1="360" x2="800" y2="360"/>
    <line x1="200" y1="0" x2="200" y2="450"/>
    <line x1="400" y1="0" x2="400" y2="450"/>
    <line x1="600" y1="0" x2="600" y2="450"/>
  </g>

  <!-- Decorative Glow Circles -->
  <circle cx="650" cy="120" r="180" fill="{style['accent']}" opacity="0.25" filter="url(#glow)"/>
  <circle cx="150" cy="380" r="140" fill="{style['highlight']}" opacity="0.15" filter="url(#glow)"/>

  <!-- Right Visual Graphic Box -->
  <g transform="translate(380, 40)">
    <rect x="0" y="0" width="360" height="240" rx="20" fill="url(#cardGrad)" stroke="#ffffff" stroke-opacity="0.2" stroke-width="1.5"/>
    <g transform="translate(-20, 0)">
      {icon_svg}
    </g>
  </g>

  <!-- Content Glass Panel -->
  <rect x="50" y="50" width="480" height="350" rx="24" fill="#0d1512" fill-opacity="0.65" stroke="#ffffff" stroke-opacity="0.15" stroke-width="1.5"/>

  <!-- Text Content -->
  <g transform="translate(85, 95)">
    <!-- Category Pill -->
    <rect x="0" y="0" width="{len(safe_category) * 11 + 24}" height="28" rx="14" fill="{style['accent']}" fill-opacity="0.3" stroke="{style['highlight']}" stroke-opacity="0.6" stroke-width="1"/>
    <text x="12" y="18" font-family="Inter, system-ui, sans-serif" font-size="11" font-weight="800" fill="{style['highlight']}" letter-spacing="1.5">{safe_category}</text>

    <!-- Title -->
    <text x="0" y="75" font-family="Inter, system-ui, sans-serif" font-size="28" font-weight="900" fill="#ffffff" letter-spacing="-0.5">
      {safe_title[:26]}
    </text>
    {"<text x='0' y='112' font-family='Inter, system-ui, sans-serif' font-size='28' font-weight='900' fill='#ffffff' letter-spacing='-0.5'>" + safe_title[26:] + "</text>" if len(safe_title) > 26 else ""}

    <!-- Subtitle / Tagline -->
    <text x="0" y="160" font-family="Inter, system-ui, sans-serif" font-size="15" font-weight="600" fill="#a0aec0">
      {subtitle}
    </text>

    <!-- Badge Row -->
    <g transform="translate(0, 200)">
      <rect x="0" y="0" width="110" height="32" rx="8" fill="#ffffff" fill-opacity="0.08" stroke="#ffffff" stroke-opacity="0.15"/>
      <text x="14" y="21" font-family="Inter, system-ui, sans-serif" font-size="12" font-weight="700" fill="#ffffff">SmartReco</text>

      <rect x="122" y="0" width="140" height="32" rx="8" fill="{style['accent']}" fill-opacity="0.25"/>
      <text x="134" y="21" font-family="Inter, system-ui, sans-serif" font-size="12" font-weight="700" fill="{style['highlight']}">★ Verified Course</text>
    </g>
  </g>
</svg>'''
    return svg_content

def main():
    generated_count = 0
    for course in SEED_COURSES:
        slug = course["slug"]
        svg = create_course_svg(slug, course["title"], course["category"])
        file_path = OUTPUT_DIR / f"{slug}.svg"
        file_path.write_text(svg, encoding="utf-8")
        generated_count += 1
    print(f"Successfully generated {generated_count} unique course thumbnail images in {OUTPUT_DIR}")

if __name__ == "__main__":
    main()
