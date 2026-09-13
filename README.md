# Signalpost Agent - Norwegian Company Information Finder

An efficient agent that retrieves Norwegian company information from public sources.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run a single company lookup
python agent.py --company_number 816716842

# Run batch processing (generates 1000 company profiles)
python agent.py --batch companies.txt --output company_profiles.json

# Run demo mode (processes 10 sample companies)
python agent.py --demo
```

## Features

- **Official Data Source**: Fetches data from Brønnøysund Register Centre (Brreg.no)
- **Rate Limiting**: Built-in rate limiting to respect API limits
- **Retry Logic**: Automatic retry on transient failures
- **Standardized Output**: Consistent JSON format for all company profiles
- **Evidence Tracking**: Each fact includes source URLs and access timestamps
- **Batch Processing**: Efficient processing of large company lists

## Output Format

Each company profile includes:
- Company number, name, status
- Registration date and address
- Industry classification (NACE codes)
- Legal form and employee count
- Contact information (phone, email, website)
- Board members and CEO
- Source citations with URLs and timestamps
- Data freshness indicators

## API Usage

- **Primary Source**: Brønnøysund Register Centre API (free, public)
- **Rate Limit**: ~2 requests/second (configurable)
- **Estimated Cost**: $0 (using free public APIs)
- **Daily Capacity**: Can process 2000+ companies within 45 minutes

## Running the Full Dataset

To generate 1000+ company profiles:

```bash
python agent.py --count 1000 --output company_profiles.json
```

Or provide your own list:

```bash
# Create companies.txt with one org number per line
python agent.py --batch companies.txt --output company_profiles.json
```

## Model/API Details

- **No LLM Required**: Uses direct API calls for deterministic results
- **External APIs**: Brreg.no (free Norwegian business register)
- **Expected Run Cost**: $0.00 (all sources are free public APIs)
- **Request Count**: ~2 requests per company (basic info + roles)

## Compliance

- Uses only permitted public sources
- Respects rate limits and terms of service
- No fabricated data - all facts sourced from official registers
- Proper evidence tracking for verification

## License

MIT License
