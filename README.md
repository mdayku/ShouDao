# ShouDao

> 销售的售 + 导游的导 = "Sales Guide"

B2B lead generation tool that turns prompts into actionable lead CSVs.

## Quick Start

```bash
# Install
pip install -e .

# Configure API keys
cp env.example .env
# Edit .env with your OPENAI_API_KEY and SERPER_API_KEY

# Check configuration
shoudao check

# Run a query
shoudao run --prompt "Large construction contractors in Florida building hotels"
```

## Output

Each run creates a folder in `runs/` with:
- `leads.csv` - Lead list with stable schema
- `leads.json` - Canonical JSON format
- `report.md` - Run summary

## CSV Schema

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

## Requirements

- Python 3.11+
- OpenAI API key
- Serper.dev API key (for search)

