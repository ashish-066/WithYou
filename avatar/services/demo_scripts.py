"""Pre-defined scripts for demo sessions.

Contains candidate profiles and response scripts that will trigger
claim verification and showcase the system's capabilities.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DemoProfile:
    """A demo candidate profile with structured verification data."""

    name: str
    job_title: str
    github_url: str | None = None
    linkedin_url: str | None = None
    resume_text: str = ""
    # Structured data for claim verification
    github_data: dict[str, Any] | None = None
    linkedin_data: dict[str, Any] | None = None
    resume_data: dict[str, Any] | None = None


@dataclass
class DemoScript:
    """A script of responses for a demo session."""

    profile: DemoProfile
    responses: list[str] = field(default_factory=list)


# =============================================================================
# Demo Profiles - Varied backgrounds with structured verification data
# =============================================================================
# Profiles are designed to have:
# - Some claims that will VERIFY (exact matches in profile data)
# - Some claims that will show CONTRADICTION (profile data differs from claims)
# - Some claims that remain UNVERIFIED (no matching data available)

DEMO_PROFILES = [
    DemoProfile(
        name="Alex Chen",
        job_title="Senior Frontend Engineer",
        github_url="https://github.com/alexchen",
        resume_text="""
ALEX CHEN
Senior Frontend Engineer | 5 years experience

EXPERIENCE:
- Frontend Lead at TechCorp (2021-2024): Led team of 5, built React dashboard
- Software Engineer at StartupXYZ (2019-2021): Developed Vue.js applications
- Junior Developer at WebAgency (2018-2019): HTML/CSS/JavaScript

SKILLS: React, TypeScript, Vue.js, Node.js, GraphQL, AWS
EDUCATION: BS Computer Science, Stanford University
        """,
        github_data={
            "name": "Alex Chen",
            "login": "alexchen",
            "public_repos": 42,
            "followers": 156,
            "top_languages": ["JavaScript", "TypeScript", "Python", "CSS"],
            "bio": "Senior frontend engineer passionate about React and modern web development",
        },
        linkedin_data={
            "name": "Alex Chen",
            "headline": "Senior Frontend Engineer",
            "experience": [
                {
                    "company": "TechCorp",
                    "title": "Frontend Lead",
                    "duration": "2021-2024",
                    "years": 3,
                },
                {
                    "company": "StartupXYZ",
                    "title": "Software Engineer",
                    "duration": "2019-2021",
                    "years": 2,
                },
            ],
            "education": [
                {"school": "Stanford University", "degree": "BS Computer Science"}
            ],
        },
        resume_data={
            "skills": [
                "React",
                "TypeScript",
                "Vue.js",
                "Node.js",
                "GraphQL",
                "AWS",
                "JavaScript",
                "CSS",
                "Redux",
                "Zustand",
                "React Query",
                "Cypress",
            ],
            "experience_years": 5,
            "education": "BS Computer Science, Stanford University",
            "companies": ["TechCorp", "StartupXYZ", "WebAgency"],
            "certifications": [],
            "team_size": 5,  # Led team of 5 - verifiable
        },
    ),
    DemoProfile(
        name="Sarah Johnson",
        job_title="Backend Engineer",
        github_url="https://github.com/sarahj-dev",
        resume_text="""
SARAH JOHNSON
Backend Engineer | 4 years experience

EXPERIENCE:
- Backend Developer at FinanceApp (2022-2024): Built microservices in Go
- Software Engineer at DataCo (2020-2022): Python/Django development
- Intern at BigTech (2019): Java backend services

SKILLS: Python, Go, PostgreSQL, Redis, Kubernetes, Docker
EDUCATION: MS Computer Science, MIT
        """,
        github_data={
            "name": "Sarah Johnson",
            "login": "sarahj-dev",
            "public_repos": 28,
            "followers": 89,
            "top_languages": ["Python", "Go", "Java", "SQL"],
            "bio": "Backend engineer building scalable systems",
        },
        linkedin_data={
            "name": "Sarah Johnson",
            "headline": "Backend Engineer at FinanceApp",
            "experience": [
                {
                    "company": "FinanceApp",
                    "title": "Backend Developer",
                    "duration": "2022-2024",
                    "years": 2,
                },
                {
                    "company": "DataCo",
                    "title": "Software Engineer",
                    "duration": "2020-2022",
                    "years": 2,
                },
            ],
            "education": [{"school": "MIT", "degree": "MS Computer Science"}],
        },
        resume_data={
            "skills": [
                "Python",
                "Go",
                "PostgreSQL",
                "Redis",
                "Kubernetes",
                "Docker",
                "OpenTelemetry",
                "Grafana",
                "microservices",
                "event sourcing",
                "CQRS",
            ],
            "experience_years": 4,
            "education": "MS Computer Science, MIT",
            "companies": ["FinanceApp", "DataCo", "BigTech"],
            "certifications": [],
        },
    ),
    DemoProfile(
        name="Marcus Williams",
        job_title="Full Stack Developer",
        github_url="https://github.com/marcusw",
        resume_text="""
MARCUS WILLIAMS
Full Stack Developer | 3 years experience

EXPERIENCE:
- Full Stack at E-commerce Inc (2022-2024): Next.js + Node.js
- Junior Developer at Agency (2021-2022): React + Express
- Bootcamp Graduate (2021)

SKILLS: JavaScript, React, Node.js, MongoDB, AWS, TypeScript
EDUCATION: Full Stack Bootcamp, Self-taught
        """,
        github_data={
            "name": "Marcus Williams",
            "login": "marcusw",
            "public_repos": 15,
            "followers": 34,
            "top_languages": ["JavaScript", "TypeScript", "HTML"],
            "bio": "Full stack developer | Bootcamp grad 2021",
        },
        linkedin_data={
            "name": "Marcus Williams",
            "headline": "Full Stack Developer",
            "experience": [
                {
                    "company": "E-commerce Inc",
                    "title": "Full Stack Developer",
                    "duration": "2022-2024",
                    "years": 2,
                },
                {
                    "company": "Agency",
                    "title": "Junior Developer",
                    "duration": "2021-2022",
                    "years": 1,
                },
            ],
            "education": [
                {"school": "Coding Bootcamp", "degree": "Full Stack Certificate"}
            ],
        },
        # CONTRADICTION: Profile shows 2 years experience, but he claims 3 years
        # Also: Claims serverless but not in skills
        resume_data={
            "skills": [
                "JavaScript",
                "React",
                "Node.js",
                "MongoDB",
                "TypeScript",
                "Next.js",
            ],
            "experience_years": 2,  # Contradicts his claim of 3 years!
            "education": "Full Stack Bootcamp",
            "companies": ["E-commerce Inc", "Agency"],
            "certifications": [],
        },
    ),
    DemoProfile(
        name="Emily Zhang",
        job_title="DevOps Engineer",
        resume_text="""
EMILY ZHANG
DevOps Engineer | 6 years experience

EXPERIENCE:
- Senior DevOps at CloudFirst (2021-2024): Kubernetes, Terraform
- DevOps Engineer at TechStartup (2018-2021): AWS, CI/CD pipelines
- Systems Admin at Enterprise (2017-2018): Linux administration

SKILLS: Kubernetes, Docker, Terraform, AWS, GCP, Python, Bash
CERTIFICATIONS: AWS Solutions Architect, CKA
EDUCATION: BS Information Technology
        """,
        github_data=None,  # No GitHub - some claims will be unverified
        linkedin_data={
            "name": "Emily Zhang",
            "headline": "Senior DevOps Engineer at CloudFirst",
            "experience": [
                {
                    "company": "CloudFirst",
                    "title": "Senior DevOps",
                    "duration": "2021-2024",
                    "years": 3,
                },
                {
                    "company": "TechStartup",
                    "title": "DevOps Engineer",
                    "duration": "2018-2021",
                    "years": 3,
                },
            ],
            "education": [
                {"school": "State University", "degree": "BS Information Technology"}
            ],
        },
        resume_data={
            "skills": [
                "Kubernetes",
                "Docker",
                "Terraform",
                "AWS",
                "GCP",
                "Python",
                "Bash",
                "GitHub Actions",
                "ArgoCD",
                "GitOps",
                "infrastructure as code",
            ],
            "experience_years": 6,
            "education": "BS Information Technology",
            "companies": ["CloudFirst", "TechStartup", "Enterprise"],
            "certifications": ["AWS Solutions Architect", "CKA"],
        },
    ),
    DemoProfile(
        name="David Park",
        job_title="Machine Learning Engineer",
        github_url="https://github.com/davidpark-ml",
        resume_text="""
DAVID PARK
Machine Learning Engineer | 4 years experience

EXPERIENCE:
- ML Engineer at AI Startup (2022-2024): Built recommendation systems
- Data Scientist at Analytics Corp (2020-2022): NLP and classification
- Research Assistant at University (2019-2020): Computer vision

SKILLS: Python, PyTorch, TensorFlow, Scikit-learn, SQL, Spark
PUBLICATIONS: 2 papers in NeurIPS
EDUCATION: PhD Machine Learning (ABD), MS Statistics
        """,
        github_data={
            "name": "David Park",
            "login": "davidpark-ml",
            "public_repos": 23,
            "followers": 245,
            "top_languages": ["Python", "Jupyter Notebook", "C++"],
            "bio": "ML Engineer | Former PhD candidate | NeurIPS author",
        },
        linkedin_data={
            "name": "David Park",
            "headline": "Machine Learning Engineer",
            "experience": [
                {
                    "company": "AI Startup",
                    "title": "ML Engineer",
                    "duration": "2022-2024",
                    "years": 2,
                },
                {
                    "company": "Analytics Corp",
                    "title": "Data Scientist",
                    "duration": "2020-2022",
                    "years": 2,
                },
            ],
            "education": [
                {"school": "Top University", "degree": "PhD Machine Learning (ABD)"},
                {"school": "Top University", "degree": "MS Statistics"},
            ],
            "publications": ["NeurIPS 2021", "NeurIPS 2022"],
        },
        resume_data={
            "skills": [
                "Python",
                "PyTorch",
                "TensorFlow",
                "Scikit-learn",
                "SQL",
                "Spark",
                "MLflow",
                "Kubeflow",
                "recommendation systems",
                "A/B testing",
            ],
            "experience_years": 4,
            "education": "PhD Machine Learning (ABD), MS Statistics",
            "companies": ["AI Startup", "Analytics Corp"],
            "certifications": [],
            "publications": 2,  # Verifiable publication count
        },
    ),
    DemoProfile(
        name="Jennifer Lee",
        job_title="Software Engineer",
        resume_text="""
JENNIFER LEE
Software Engineer | 2 years experience

EXPERIENCE:
- Software Engineer at MidSize Tech (2023-2024): Java microservices
- Junior Developer at Startup (2022-2023): Python backend
- Intern at FAANG (2021): Internal tools

SKILLS: Java, Python, Spring Boot, React, PostgreSQL, Docker
EDUCATION: BS Computer Science, UC Berkeley
        """,
        github_data=None,  # No GitHub profile
        linkedin_data={
            "name": "Jennifer Lee",
            "headline": "Software Engineer",
            "experience": [
                {
                    "company": "MidSize Tech",
                    "title": "Software Engineer",
                    "duration": "2023-2024",
                    "years": 1,
                },
                {
                    "company": "Startup",
                    "title": "Junior Developer",
                    "duration": "2022-2023",
                    "years": 1,
                },
            ],
            "education": [{"school": "UC Berkeley", "degree": "BS Computer Science"}],
        },
        resume_data={
            "skills": [
                "Java",
                "Python",
                "Spring Boot",
                "React",
                "PostgreSQL",
                "Docker",
                "Go",
            ],
            "experience_years": 2,
            "education": "BS Computer Science, UC Berkeley",
            "companies": ["MidSize Tech", "Startup", "FAANG"],
            "certifications": [],
        },
    ),
    DemoProfile(
        name="Ryan Thompson",
        job_title="Platform Engineer",
        github_url="https://github.com/ryant-platform",
        resume_text="""
RYAN THOMPSON
Platform Engineer | 7 years experience

EXPERIENCE:
- Staff Engineer at ScaleUp (2021-2024): Platform team lead
- Senior Engineer at Unicorn (2018-2021): Infrastructure
- Engineer at Consulting (2017-2018): Various projects

SKILLS: Go, Rust, Kubernetes, Service Mesh, Observability
EDUCATION: MS Computer Engineering
        """,
        github_data={
            "name": "Ryan Thompson",
            "login": "ryant-platform",
            "public_repos": 67,
            "followers": 512,
            "top_languages": ["Go", "Rust", "Python", "Shell"],
            "bio": "Staff platform engineer | Building infrastructure at scale",
        },
        linkedin_data={
            "name": "Ryan Thompson",
            "headline": "Staff Platform Engineer",
            "experience": [
                {
                    "company": "ScaleUp",
                    "title": "Staff Engineer",
                    "duration": "2021-2024",
                    "years": 3,
                },
                {
                    "company": "Unicorn",
                    "title": "Senior Engineer",
                    "duration": "2018-2021",
                    "years": 3,
                },
            ],
            "education": [
                {"school": "Tech University", "degree": "MS Computer Engineering"}
            ],
        },
        # CONTRADICTION: Claims 7 years but profile only shows 6
        # Also: Claims team of 500 engineers served, but actual is ~200
        resume_data={
            "skills": [
                "Go",
                "Rust",
                "Kubernetes",
                "Service Mesh",
                "Observability",
                "developer portal",
            ],
            "experience_years": 6,  # Contradicts his claim of 7 years!
            "education": "MS Computer Engineering",
            "companies": ["ScaleUp", "Unicorn", "Consulting"],
            "certifications": [],
            "team_size": 200,  # Says 500 in script - CONTRADICTION
        },
    ),
    DemoProfile(
        name="Priya Sharma",
        job_title="Security Engineer",
        resume_text="""
PRIYA SHARMA
Security Engineer | 5 years experience

EXPERIENCE:
- Security Engineer at FinTech (2022-2024): AppSec, penetration testing
- Security Analyst at Enterprise (2020-2022): SIEM, incident response
- Junior Security at Consulting (2019-2020): Vulnerability assessment

SKILLS: Python, Burp Suite, AWS Security, OWASP, Compliance
CERTIFICATIONS: OSCP, AWS Security Specialty
EDUCATION: BS Cybersecurity
        """,
        github_data=None,  # Security engineers often don't have public GitHub
        linkedin_data={
            "name": "Priya Sharma",
            "headline": "Security Engineer",
            "experience": [
                {
                    "company": "FinTech",
                    "title": "Security Engineer",
                    "duration": "2022-2024",
                    "years": 2,
                },
                {
                    "company": "Enterprise",
                    "title": "Security Analyst",
                    "duration": "2020-2022",
                    "years": 2,
                },
            ],
            "education": [{"school": "Cyber University", "degree": "BS Cybersecurity"}],
        },
        # CONTRADICTION: Claims OSCP but it's not in certifications
        resume_data={
            "skills": [
                "Python",
                "Burp Suite",
                "AWS Security",
                "OWASP",
                "Compliance",
                "threat modeling",
                "SOC 2",
                "security scanning",
            ],
            "experience_years": 5,
            "education": "BS Cybersecurity",
            "companies": ["FinTech", "Enterprise", "Consulting"],
            # Note: OSCP is missing from certifications - she claims it but it's not verified
            "certifications": ["AWS Security Specialty"],  # Missing OSCP!
        },
    ),
]


# =============================================================================
# Demo Response Scripts - Designed to trigger claim verification
# =============================================================================

# Each response list simulates a candidate's answers during an interview
# Responses are designed to make verifiable claims that match profile data
# Script order matches DEMO_PROFILES order for proper pairing

DEMO_RESPONSE_SCRIPTS = [
    # Script 1: Alex Chen - Senior Frontend Engineer (matches profile 1)
    # Verifiable: React, TypeScript, Stanford, 5 years, team of 5, TechCorp
    [
        "Hi! Thanks for having me. I'm excited to discuss this opportunity.",
        "I've been working as a senior frontend engineer for about 5 years now, mostly with React and TypeScript.",
        "At TechCorp, I led a team of 5 engineers to rebuild our entire dashboard from scratch. We improved load time by 60%.",
        "Yes, I'm very comfortable with state management. I've used Redux extensively, and more recently Zustand and React Query.",
        "For testing, I believe in a pyramid approach. We had about 80% unit test coverage and used Cypress for E2E tests.",
        "I graduated from Stanford University with a BS in Computer Science.",
        "The biggest challenge was migrating from class components to hooks while maintaining backward compatibility.",
        "I'd love to learn more about your tech stack and the problems you're trying to solve.",
    ],
    # Script 2: Sarah Johnson - Backend Engineer (matches profile 2)
    # Verifiable: Go, Python, PostgreSQL, MIT, FinanceApp, 4 years
    [
        "Hello! Great to meet you. I've been looking forward to this conversation.",
        "I specialize in backend development, primarily using Go and Python. I've built several microservices at scale.",
        "At FinanceApp, I designed a payment processing system that handles over 10,000 transactions per second.",
        "We used event sourcing and CQRS patterns to ensure data consistency across our distributed system.",
        "I have extensive experience with PostgreSQL and Redis. We reduced query latency by 40% through careful indexing.",
        "For observability, we implemented OpenTelemetry across all services with custom dashboards in Grafana.",
        "I graduated from MIT with a masters in computer science, focusing on distributed systems.",
        "I'm particularly interested in the scaling challenges your platform faces.",
    ],
    # Script 3: Marcus Williams - Full Stack (matches profile 3)
    # CONTRADICTION: Claims 3 years but profile shows 2 years
    [
        "Hey! Great to meet you. I'm excited about this full stack position.",
        "I've been building web applications for about 3 years now.",
        "I'm comfortable with both frontend and backend, though I lean slightly toward frontend.",
        "I taught myself to code through online resources and a bootcamp.",
        "At E-commerce Inc, I built an e-commerce platform that processes thousands of orders daily.",
        "I use Next.js and Node.js most frequently, with MongoDB for the database.",
        "I'm always learning new things. Recently I've been exploring serverless architectures.",
        "What's the team structure like here?",
    ],
    # Script 4: Emily Zhang - DevOps Engineer (matches profile 4)
    # Verifiable: AWS Solutions Architect, CKA, 6 years, CloudFirst, Kubernetes
    [
        "Hi there! Thanks for the opportunity to interview.",
        "I'm a DevOps engineer with 6 years of experience, primarily in cloud infrastructure.",
        "I'm AWS Solutions Architect certified and also have my CKA for Kubernetes.",
        "At CloudFirst, I reduced our infrastructure costs by 35% through right-sizing and spot instances.",
        "I built our entire CI/CD pipeline using GitHub Actions and ArgoCD for GitOps deployment.",
        "We managed over 200 microservices across 3 Kubernetes clusters with zero downtime deployments.",
        "I'm passionate about infrastructure as code. Everything I build is versioned in Terraform.",
        "What does your current deployment process look like?",
    ],
    # Script 5: David Park - ML Engineer (matches profile 5)
    # Verifiable: PhD, 2 papers, NeurIPS, PyTorch, AI Startup, 4 years
    [
        "Hello! I'm thrilled to be here discussing this ML role.",
        "I have a PhD background in machine learning, though I left academia to work in industry.",
        "I've published 2 papers at NeurIPS on recommendation systems and personalization.",
        "At AI Startup, I built a recommendation engine that increased user engagement by 25%.",
        "I'm very comfortable with PyTorch and have contributed to some open source ML libraries.",
        "For MLOps, we use MLflow for experiment tracking and Kubeflow for model serving.",
        "I led the implementation of A/B testing infrastructure for our ML models.",
        "I'd love to hear about the ML challenges you're working on.",
    ],
    # Script 6: Jennifer Lee - Software Engineer (matches profile 6)
    # Verifiable: UC Berkeley, Java, Python, 2 years, FAANG intern
    [
        "Hi! Thank you so much for this opportunity. I'm really excited to be here.",
        "I graduated from UC Berkeley last year with a degree in computer science.",
        "I did an internship at a big tech company where I worked on internal tools.",
        "I'm most comfortable with Java and Python, and I've been learning Go on the side.",
        "For my senior project, I built a distributed key-value store. It was challenging but I learned a lot.",
        "I'm really eager to learn and grow. I know I'm early in my career but I'm a fast learner.",
        "I've been contributing to open source to build my skills. Mostly documentation and bug fixes so far.",
        "What does the onboarding process look like for new engineers?",
    ],
    # Script 7: Ryan Thompson - Platform Engineer (matches profile 7)
    # CONTRADICTION: Claims 7 years but profile shows 6 years
    # CONTRADICTION: Claims serves 500 engineers but profile shows 200
    [
        "Good morning! Thanks for taking the time to chat.",
        "I'm a platform engineer with 7 years of experience building developer platforms.",
        "At my current company, I lead the platform team that serves over 500 engineers.",
        "We built an internal developer portal that reduced onboarding time from 2 weeks to 2 days.",
        "I primarily work in Go and Rust for performance-critical services.",
        "Our platform handles service mesh, observability, and self-service infrastructure provisioning.",
        "I'm passionate about developer experience. Happy developers are productive developers.",
        "How autonomous are your engineering teams currently?",
    ],
    # Script 8: Priya Sharma - Security Engineer (matches profile 8)
    # CONTRADICTION: Claims OSCP but not in certifications
    # Verifiable: AWS Security, FinTech, 5 years, threat modeling, SOC 2
    [
        "Hello! Security engineering is my passion, so I'm excited about this role.",
        "I have my OSCP certification and 5 years of hands-on security experience.",
        "I specialize in application security and have found several critical vulnerabilities in production systems.",
        "At FinTech, I built our security scanning pipeline that catches issues before they reach production.",
        "I'm experienced with threat modeling and have led several security architecture reviews.",
        "Compliance is also part of my expertise. I helped achieve SOC 2 Type II certification.",
        "I believe security should enable the business, not block it.",
        "What's your current security posture and what are you looking to improve?",
    ],
]


def get_demo_scripts(count: int = 10) -> list[DemoScript]:
    """Get a list of demo scripts for the scalability demo.

    Args:
        count: Number of scripts to generate

    Returns:
        List of DemoScript objects
    """
    scripts = []

    for i in range(count):
        profile_idx = i % len(DEMO_PROFILES)
        script_idx = i % len(DEMO_RESPONSE_SCRIPTS)

        profile = DEMO_PROFILES[profile_idx]
        responses = DEMO_RESPONSE_SCRIPTS[script_idx]

        # Create a unique name if we're reusing profiles
        if i >= len(DEMO_PROFILES):
            profile = DemoProfile(
                name=f"{profile.name} #{i + 1}",
                job_title=profile.job_title,
                github_url=profile.github_url,
                linkedin_url=profile.linkedin_url,
                resume_text=profile.resume_text,
                github_data=profile.github_data,
                linkedin_data=profile.linkedin_data,
                resume_data=profile.resume_data,
            )

        scripts.append(DemoScript(profile=profile, responses=responses))

    return scripts
