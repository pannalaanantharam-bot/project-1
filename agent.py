#!/usr/bin/env python3
"""
Signalpost Agent - Norwegian Company Information Finder

This agent fetches company information from the Norwegian Brønnøysund Register Centre (Brreg.no)
and other permitted public sources.

Usage: python agent.py --company_number <org_number>
       python agent.py --batch <input_file> --output <output_file>
"""

import argparse
import json
import os
import sys
import time
import hashlib
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, asdict
import requests
from requests.adapters import HTTPAdapter, Retry


# Configuration
BRREG_API_BASE = "https://data.brreg.no/enhetsregisteret/api"
BRREG_TIMEOUT = 10
MAX_RETRIES = 3
REQUEST_DELAY = 0.1  # Minimal delay for efficiency (within API limits)
BATCH_REQUEST_DELAY = 0.05  # Even faster within batch processing


@dataclass
class CompanyProfile:
    """Standardized company profile structure"""
    company_number: str
    name: str
    status: str
    registration_date: Optional[str]
    address: Optional[str]
    postal_code: Optional[str]
    city: Optional[str]
    country: str
    industry_code: Optional[str]
    industry_description: Optional[str]
    legal_form: Optional[str]
    employee_count: Optional[str]
    website: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    board_members: List[Dict[str, Any]]
    ceo: Optional[str]
    financial_year_end: Optional[str]
    share_capital: Optional[str]
    sources: List[Dict[str, str]]
    last_updated: str
    data_freshness_days: int
    
    def to_dict(self) -> Dict:
        return asdict(self)


class BrregClient:
    """Client for Norwegian Brønnøysund Register Centre API"""
    
    def __init__(self):
        self.session = requests.Session()
        retry_strategy = Retry(
            total=MAX_RETRIES,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.headers.update({
            'User-Agent': 'Signalpost-Agent/1.0 (Company Information Retrieval)',
            'Accept': 'application/json'
        })
        self.last_request_time = 0
    
    def _rate_limit(self):
        """Implement rate limiting"""
        elapsed = time.time() - self.last_request_time
        if elapsed < REQUEST_DELAY:
            time.sleep(REQUEST_DELAY - elapsed)
        self.last_request_time = time.time()
    
    def get_company(self, org_number: str) -> Optional[Dict]:
        """Fetch company basic info from Brreg"""
        self._rate_limit()
        # Remove any spaces or dashes from org number
        org_number = org_number.replace(" ", "").replace("-", "")
        
        url = f"{BRREG_API_BASE}/enheter/{org_number}"
        # Don't include params that might cause 400 errors
        
        try:
            response = self.session.get(url, timeout=BRREG_TIMEOUT)
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                return None
            else:
                print(f"Warning: API returned {response.status_code} for {org_number}")
                return None
        except requests.RequestException as e:
            print(f"Error fetching {org_number}: {e}")
            return None
    
    def get_roles(self, org_number: str) -> Optional[Dict]:
        """Fetch company roles (board, CEO, etc.) from Brreg"""
        self._rate_limit()
        org_number = org_number.replace(" ", "").replace("-", "")
        
        url = f"{BRREG_API_BASE}/roller/{org_number}"
        
        try:
            response = self.session.get(url, params={'size': 50}, timeout=BRREG_TIMEOUT)
            if response.status_code == 200:
                return response.json()
            return None
        except requests.RequestException:
            return None


def parse_brreg_company(data: Dict, org_number: str) -> CompanyProfile:
    """Parse Brreg API response into standardized CompanyProfile"""
    
    # Extract basic info
    navn = data.get('navn', '')
    status = data.get('status', 'NORMAL')
    
    # Registration date
    registreringsdato = data.get('registreringsDatoFraEnheten')
    registration_date = None
    if registreringsdato:
        registration_date = registreringsdato[:10] if len(registreringsdato) >= 10 else registreringsdato
    
    # Address
    forretningsadresse = data.get('forretningsadresse', {})
    adresse = forretningsadresse.get('adresse', [])
    address = ', '.join(adresse) if adresse else None
    postnummer = forretningsadresse.get('postnummer')
    poststed = forretningsadresse.get('poststed')
    postal_code = str(postnummer) if postnummer else None
    city = poststed if isinstance(poststed, str) else (poststed.get('beskrivelse') if isinstance(poststed, dict) else None)
    
    # Country
    land = forretningsadresse.get('land')
    country = land.get('kode') if isinstance(land, dict) else (land if land else 'NO')
    
    # Industry
    naeringskode1 = data.get('naeringskode1', {})
    industry_code = naeringskode1.get('kode') if isinstance(naeringskode1, dict) else None
    industry_description = naeringskode1.get('beskrivelse') if isinstance(naeringskode1, dict) else None
    
    # Legal form
    organisasjonsform = data.get('organisasjonsform', {})
    legal_form = organisasjonsform.get('beskrivelse') if isinstance(organisasjonsform, dict) else None
    
    # Employee count
    antall_ansatte = data.get('antallAnsatte')
    employee_count = str(antall_ansatte) if antall_ansatte is not None else None
    
    # Contact info
    kontaktinfo = data.get('kontaktinformasjon', {})
    telefon = kontaktinfo.get('telefonnummer')
    telefaks = kontaktinfo.get('telefaksnummer')
    epost = kontaktinfo.get('epostadresse')
    
    phone = telefon if telefon else None
    email = epost if epost else None
    
    # Website
    website = None
    hjemmeside = data.get('hjemmeside')
    if hjemmeside:
        website = hjemmeside if isinstance(hjemmeside, str) else hjemmeside.get('url')
    
    # Stiftelsesdato (founding date)
    stiftelsesdato = data.get('stiftelsesdato')
    if stiftelsesdato and not registration_date:
        registration_date = stiftelsesdato[:10] if len(stiftelsesdato) >= 10 else stiftelsesdato
    
    # Board members and CEO from roles
    board_members = []
    ceo = None
    
    # Financial info (not directly available in basic API)
    financial_year_end = None
    share_capital = None
    
    # Try to get capital info
    kapital = data.get('kapital', {})
    if kapital and isinstance(kapital, dict):
        belop = kapital.get('belop')
        if belop:
            valuta = kapital.get('valuta', 'NOK')
            share_capital = f"{belop} {valuta}"
    
    # Sources
    sources = [{
        'name': 'Brønnøysund Register Centre',
        'url': f'https://www.brreg.no/enhet/{org_number}',
        'accessed': datetime.now(timezone.utc).isoformat(),
        'type': 'official_register'
    }]
    
    # Calculate data freshness
    last_updated = datetime.now(timezone.utc).isoformat()
    data_freshness_days = 0  # Fresh data
    
    return CompanyProfile(
        company_number=org_number,
        name=navn,
        status=status,
        registration_date=registration_date,
        address=address,
        postal_code=postal_code,
        city=city,
        country=country,
        industry_code=industry_code,
        industry_description=industry_description,
        legal_form=legal_form,
        employee_count=employee_count,
        website=website,
        phone=phone,
        email=email,
        board_members=board_members,
        ceo=ceo,
        financial_year_end=financial_year_end,
        share_capital=share_capital,
        sources=sources,
        last_updated=last_updated,
        data_freshness_days=data_freshness_days
    )


def generate_sample_companies(count: int = 1000) -> List[str]:
    """Generate sample Norwegian company numbers for testing/demo"""
    # Fetch real company numbers from Brreg API
    companies = []
    
    # Some real Norwegian company numbers (publicly known)
    known_companies = [
        "995849364",  # :-) INVEST AS
        "929943945",  # !FALSE INVESTMENTS AS
        "986467491",  # ¡ HOLY TOLEDO !
        "989061593",  # -G- GROUP AS
        "819032262",  # ...PIECE OF CAKE AS
        "935845114",  # .BEIN BERGEN AS
        "923569839",  # .EAGL TECHNOLOGIES AS
        "916627939",  # - P A L M E R A -
        "933365573",  # - ZOTKO .NO
        "934551435",  # ----ADVOKATFIRMAET CATO MYHRE
    ]
    
    # Add known companies first
    companies.extend(known_companies[:min(len(known_companies), count)])
    
    if len(companies) >= count:
        return companies[:count]
    
    # Fetch additional real companies from Brreg API
    print(f"Fetching {count - len(companies)} additional companies from Brreg API...")
    client = BrregClient()
    page = 0
    session = requests.Session()
    session.headers.update({'Accept': 'application/json'})
    
    while len(companies) < count:
        try:
            url = f"{BRREG_API_BASE}/enheter"
            params = {'page': page, 'size': 20}
            response = session.get(url, params=params, timeout=BRREG_TIMEOUT)
            
            if response.status_code != 200:
                break
                
            data = response.json()
            embedded = data.get('_embedded', {})
            enheter = embedded.get('enheter', [])
            
            if not enheter:
                break
                
            for enhet in enheter:
                org_nr = enhet.get('organisasjonsnummer')
                if org_nr and org_nr not in companies:
                    companies.append(org_nr)
                    if len(companies) >= count:
                        break
            
            page += 1
            
            # Rate limiting
            time.sleep(REQUEST_DELAY)
            
        except Exception as e:
            print(f"Error fetching company list: {e}")
            break
    
    return companies[:count]


def process_company(client: BrregClient, org_number: str) -> Optional[CompanyProfile]:
    """Process a single company number and return profile"""
    print(f"Processing company: {org_number}")
    
    # Fetch from Brreg
    company_data = client.get_company(org_number)
    
    if not company_data:
        print(f"  No data found for {org_number}")
        return None
    
    # Parse into standardized profile
    profile = parse_brreg_company(company_data, org_number)
    
    # Fetch additional role information
    roles_data = client.get_roles(org_number)
    if roles_data and '_embedded' in roles_data:
        embedded = roles_data['_embedded']
        
        # Extract board members
        if 'rolleListe' in embedded:
            for role_item in embedded['rolleListe']:
                roller = role_item.get('roller', [])
                for rolle in roller:
                    person = rolle.get('person', {})
                    navn = person.get('navn', '')
                    verv = rolle.get('verv', {}).get('beskrivelse', '') if isinstance(rolle.get('verv'), dict) else ''
                    
                    if navn:
                        if 'styremedlem' in verv.lower() or 'board' in verv.lower():
                            profile.board_members.append({
                                'name': navn,
                                'role': verv,
                                'appointed': rolle.get('gyldigFra', '')
                            })
                        elif 'daglig leder' in verv.lower() or 'ceo' in verv.lower():
                            profile.ceo = navn
    
    print(f"  Found: {profile.name}")
    return profile


def run_batch(input_file: Optional[str], output_file: str, count: int = 1000):
    """Run batch processing of companies"""
    
    client = BrregClient()
    profiles = []
    
    # Get company numbers
    if input_file and os.path.exists(input_file):
        with open(input_file, 'r') as f:
            org_numbers = [line.strip() for line in f if line.strip()]
    else:
        org_numbers = generate_sample_companies(count)
    
    print(f"Processing {len(org_numbers)} companies...")
    
    start_time = time.time()
    successful = 0
    failed = 0
    
    for i, org_num in enumerate(org_numbers):
        try:
            profile = process_company(client, org_num)
            if profile:
                profiles.append(profile.to_dict())
                successful += 1
            else:
                failed += 1
        except Exception as e:
            print(f"Error processing {org_num}: {e}")
            failed += 1
        
        # Progress update every 50 companies
        if (i + 1) % 50 == 0:
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            print(f"Progress: {i+1}/{len(org_numbers)} ({successful} success, {failed} failed, {rate:.1f} req/s)")
    
    # Save results
    output_data = {
        'metadata': {
            'total_requested': len(org_numbers),
            'successful': successful,
            'failed': failed,
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'agent_version': '1.0.0',
            'sources_used': ['Brønnøysund Register Centre (Brreg.no)']
        },
        'profiles': profiles
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    elapsed = time.time() - start_time
    print(f"\nCompleted in {elapsed:.1f}s")
    print(f"Results: {successful} successful, {failed} failed")
    print(f"Output saved to: {output_file}")
    
    return output_data


def main():
    parser = argparse.ArgumentParser(description='Signalpost Agent - Norwegian Company Information Finder')
    parser.add_argument('--company_number', '-c', type=str, help='Single company number to lookup')
    parser.add_argument('--batch', '-b', type=str, help='Input file with company numbers (one per line)')
    parser.add_argument('--output', '-o', type=str, default='company_profiles.json', help='Output JSON file')
    parser.add_argument('--count', '-n', type=int, default=1000, help='Number of companies to generate if no input file')
    parser.add_argument('--demo', action='store_true', help='Run demo with sample companies')
    
    args = parser.parse_args()
    
    if args.company_number:
        # Single company lookup
        client = BrregClient()
        profile = process_company(client, args.company_number)
        if profile:
            print("\n" + "="*60)
            print(json.dumps(profile.to_dict(), indent=2, ensure_ascii=False))
        else:
            print(f"No data found for company number: {args.company_number}")
            sys.exit(1)
    
    elif args.batch or args.demo:
        # Batch processing
        run_batch(args.batch, args.output, args.count)
    
    else:
        # Default: run demo with just 10 companies for quick testing
        print("Running demo mode with 10 sample companies...")
        run_batch(None, args.output, 10)


if __name__ == '__main__':
    main()
