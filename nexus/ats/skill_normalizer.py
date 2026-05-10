SKILL_ALIASES = {
    "ml": "machine learning",
    "ai": "artificial intelligence",
    "js": "javascript",
    "ts": "typescript",
    "py": "python",
    "k8s": "kubernetes",
    "tf": "tensorflow",
    "dl": "deep learning",
    "nlp": "natural language processing",
    "cv": "computer vision",
    "be": "backend",
    "fe": "frontend",
    "c++": "cpp",
    "c#": "csharp",
    "next": "nextjs",
    "next.js": "nextjs",
    "react.js": "react",
    "vue.js": "vue",
    "node.js": "node",
    "nodejs": "node",
    "express.js": "express",
    "expressjs": "express",
    "postgres": "postgresql",
    "pg": "postgresql",
    "sklearn": "scikit-learn",
    "scikit": "scikit-learn",
    "gcp": "google cloud",
    "aws": "amazon web services",
    "azure": "microsoft azure",
    "jsx": "react",
    "tsx": "typescript",
    "prisma": "prisma orm",
    "typeorm": "typeorm",
}

SKILL_DOMAINS = {
    "frontend": [
        "react",
        "vue",
        "angular",
        "html",
        "css",
        "javascript",
        "typescript",
        "nextjs",
        "svelte",
        "tailwind",
        "bootstrap",
        "webpack",
        "vite",
    ],
    "backend": [
        "python",
        "fastapi",
        "django",
        "flask",
        "node",
        "express",
        "java",
        "spring",
        "spring boot",
        "golang",
        "go",
        "rust",
        "ruby",
        "rails",
        "php",
        "laravel",
        "graphql",
        "rest api",
    ],
    "ml": [
        "tensorflow",
        "pytorch",
        "scikit-learn",
        "machine learning",
        "deep learning",
        "nlp",
        "computer vision",
        "keras",
        "jax",
        "hugging face",
        "transformers",
        "langchain",
        "llm",
        "rag",
    ],
    "devops": [
        "docker",
        "kubernetes",
        "aws",
        "gcp",
        "azure",
        "terraform",
        "ci/cd",
        "github actions",
        "jenkins",
        "ansible",
        "helm",
        "prometheus",
        "grafana",
        "linux",
    ],
    "data": [
        "sql",
        "postgresql",
        "mongodb",
        "pandas",
        "numpy",
        "spark",
        "kafka",
        "airflow",
        "snowflake",
        "bigquery",
        "redshift",
        "dbt",
        "etl",
        "data pipeline",
    ],
    "mobile": [
        "react native",
        "flutter",
        "swift",
        "kotlin",
        "android",
        "ios",
        "dart",
        "xamarin",
    ],
    "security": [
        "cybersecurity",
        "penetration testing",
        "ethical hacking",
        "network security",
        "cryptography",
        "owasp",
        "soc",
        "incident response",
    ],
    "product": [
        "product management",
        "product strategy",
        "roadmapping",
        "a/b testing",
        "analytics",
        "user research",
        "agile",
        "scrum",
    ],
}


def normalize_skills(skills: list[str]) -> list[str]:
    seen = set()
    result = []
    for skill in skills:
        normalized = skill.strip().lower()
        resolved = SKILL_ALIASES.get(normalized, normalized)
        if resolved not in seen:
            seen.add(resolved)
            result.append(resolved)
    return result


def get_skill_domains(skills: list[str]) -> dict[str, list[str]]:
    normalized = normalize_skills(skills)
    skill_set = set(normalized)
    domains = {}
    for domain, domain_skills in SKILL_DOMAINS.items():
        matched = [s for s in domain_skills if s in skill_set]
        if matched:
            domains[domain] = matched
    return domains


def jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0
