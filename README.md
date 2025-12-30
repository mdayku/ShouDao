# ShouDao

> 销售的售 + 导游的导 = "Sales Guide"

B2B lead generation and talent discovery tool that turns prompts into actionable CSVs.

## Quick Start

```bash
# Install
pip install -e .

# Configure API keys
cp env.example .env
# Edit .env with your OPENAI_API_KEY, SERPER_API_KEY, and optionally APIFY_API_KEY

# Check configuration
shoudao check

# Run a lead generation query
shoudao run --prompt "Large construction contractors in Florida building hotels"

# Run a talent discovery query
shoudao talent --prompt "software engineers with AI experience"

# Run talent discovery with LinkedIn
shoudao talent --linkedin --prompt "ML engineers startup experience" --max-results 25
```

## Commands

### Lead Generation
```bash
shoudao run --prompt "..."           # Generate B2B leads
shoudao recipe create --prompt "..." # Save query as recipe
shoudao recipe run <slug>            # Rerun saved recipe
```

### Talent Discovery
```bash
shoudao talent --prompt "..."                    # Web-sourced candidates
shoudao talent --linkedin --prompt "..."         # LinkedIn-sourced candidates
shoudao talent --linkedin --linkedin-mode Full   # Detailed profile scraping
```

## Output

Each run creates a folder in `runs/` with:
- `leads.csv` / `candidates.csv` - Lead/candidate list
- `leads.json` / `candidates.json` - Canonical JSON format
- `leads.xlsx` / `candidates.xlsx` - Excel format
- `report.md` - Run summary

## Lead CSV Schema

| Column | Description |
|--------|-------------|
| company_name | Company name |
| company_type | contractor/developer/supplier/distributor/other |
| country_or_territory | Location |
| website | Primary domain |
| contact_name | Contact full name |
| email_public | Public email if found |
| evidence_urls | Source URLs (semicolon-separated) |
| confidence | Quality score 0-1 |
| recommended_angle | Outreach angle |
| qualifying_question | Question to qualify |

## Candidate CSV Schema

| Column | Description |
|--------|-------------|
| name | Candidate name |
| linkedin_url | LinkedIn profile |
| current_role | Job title |
| current_company | Employer |
| location | Geographic location |
| degree_signal | Education (degree, school) |
| years_experience | Estimated experience |
| tier | A/B/C fit classification |
| score | Quality score 0-1 |
| salary_band | Estimated salary range |

## Requirements

- Python 3.11+
- OpenAI API key (required)
- Serper.dev API key (for web search)
- Apify API key (for LinkedIn, optional)

