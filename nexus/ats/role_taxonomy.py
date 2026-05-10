ROLE_TAXONOMY = {
    "software_engineer": [
        "software engineer",
        "software developer",
        "sde",
        "swe",
        "backend developer",
        "backend engineer",
        "fullstack",
        "full stack",
        "full-stack",
        "software engineering intern",
    ],
    "ml_engineer": [
        "ml engineer",
        "machine learning engineer",
        "ai engineer",
        "ai/ml",
        "ai/ml engineer",
        "ml developer",
        "deep learning engineer",
    ],
    "data_scientist": [
        "data scientist",
        "data analyst",
        "data engineer",
        "analytics engineer",
        "data science intern",
    ],
    "frontend_engineer": [
        "frontend developer",
        "frontend engineer",
        "ui developer",
        "react developer",
        "web developer",
        "frontend engineering intern",
    ],
    "devops_engineer": [
        "devops",
        "sre",
        "platform engineer",
        "cloud engineer",
        "infrastructure engineer",
        "devops engineer",
    ],
    "product_manager": [
        "product manager",
        "pm",
        "product analyst",
        "associate pm",
        "product management intern",
    ],
    "design": [
        "ui designer",
        "ux designer",
        "product designer",
        "visual designer",
        "graphic designer",
        "design intern",
    ],
    "research": [
        "research intern",
        "research engineer",
        "research scientist",
        "ml researcher",
        "ai researcher",
    ],
}


def map_roles_to_taxonomy(roles: list[str]) -> set[str]:
    matched = set()
    for role in roles:
        role_lower = role.lower().strip()
        for tax_key, role_patterns in ROLE_TAXONOMY.items():
            for pattern in role_patterns:
                if pattern in role_lower or role_lower in pattern:
                    matched.add(tax_key)
                    break
    return matched


def taxonomy_overlap(profile_tax: set[str], job_title: str) -> float:
    if not profile_tax or not job_title:
        return 0.0
    job_lower = job_title.lower()
    for tax_key, role_patterns in ROLE_TAXONOMY.items():
        if tax_key in profile_tax:
            for pattern in role_patterns:
                if pattern in job_lower or job_lower in pattern:
                    return 1.0
        for pattern in role_patterns:
            if pattern in job_lower or job_lower in pattern:
                if tax_key in profile_tax:
                    return 1.0
    return 0.0
