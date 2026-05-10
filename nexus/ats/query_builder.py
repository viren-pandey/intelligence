def build_search_queries(ats_signals: dict) -> list[str]:
    queries = []
    skills = ats_signals.get("normalized_skills", [])
    roles = ats_signals.get("role_taxonomy", [])
    locations = ats_signals.get("location_preference", [])
    remote = ats_signals.get("remote_required", False)
    graduation_year = ats_signals.get("graduation_year", "")
    companies = ats_signals.get("companies_of_interest", [])
    interest_clusters = ats_signals.get("interest_clusters", [])

    skill_str = " ".join(f'"{s}"' for s in skills[:4])
    role_keywords = _role_to_keywords(roles)

    if role_keywords and skill_str:
        queries.append(f"{role_keywords} {skill_str} intern {graduation_year} apply")
        queries.append(
            f"{role_keywords} {skill_str} internship {graduation_year} remote"
        )

    if role_keywords:
        for loc in locations[:2]:
            queries.append(
                f"{role_keywords} internship {loc} {graduation_year} stipend"
            )
        queries.append(f"{role_keywords} fresher {graduation_year} hiring")

    if skill_str:
        queries.append(f"{skill_str} intern 2025 apply")
        queries.append(f'{skill_str} internship "we are hiring"')
        queries.append(f'{skill_str} "open position" intern')

    if remote and role_keywords:
        queries.append(f"{role_keywords} remote internship {graduation_year}")
        queries.append(f'"remote-first" {role_keywords} intern apply')

    for cluster in interest_clusters:
        queries.append(f'"{cluster}" internship {graduation_year} apply')
        queries.append(f'"{cluster}" intern hiring remote')

    if graduation_year:
        yr = str(graduation_year)
        queries.append(f'"batch {yr}" internship apply')
        next_yr = str(int(yr) + 1)
        queries.append(f'"batch {next_yr}" internship apply')

    if remote:
        queries.append(f'"remote-first" internship {skill_str}')

    if companies:
        for company in companies[:5]:
            queries.append(
                f"site:{company.lower().replace(' ', '')}.com/careers intern"
            )
            queries.append(f'"{company}" internship hiring {graduation_year}')

    queries.append(f'internship {graduation_year} batch "apply"')
    queries.append(f"fresher software intern {graduation_year}")

    seen = set()
    unique_queries = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            unique_queries.append(q)

    return unique_queries[:25]


def _role_to_keywords(roles: list[str]) -> str:
    mapping = {
        "software_engineer": '"software engineer" OR "backend" OR "fullstack"',
        "ml_engineer": '"machine learning" OR "ML engineer" OR "AI engineer"',
        "data_scientist": '"data scientist" OR "data analyst"',
        "frontend_engineer": '"frontend" OR "react developer"',
        "devops_engineer": '"devops" OR "platform engineer"',
        "product_manager": '"product manager" OR "PM"',
        "design": '"UI designer" OR "UX designer" OR "product designer"',
        "research": '"research intern" OR "research engineer"',
    }
    keywords = [mapping.get(r, r) for r in roles if r in mapping]
    return " OR ".join(keywords[:2]) if keywords else ""
