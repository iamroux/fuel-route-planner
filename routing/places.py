import re

US_STATES = {
    'AL': 'Alabama', 'AK': 'Alaska', 'AZ': 'Arizona', 'AR': 'Arkansas', 'CA': 'California',
    'CO': 'Colorado', 'CT': 'Connecticut', 'DE': 'Delaware', 'DC': 'District of Columbia',
    'FL': 'Florida', 'GA': 'Georgia', 'HI': 'Hawaii', 'ID': 'Idaho', 'IL': 'Illinois',
    'IN': 'Indiana', 'IA': 'Iowa', 'KS': 'Kansas', 'KY': 'Kentucky', 'LA': 'Louisiana',
    'ME': 'Maine', 'MD': 'Maryland', 'MA': 'Massachusetts', 'MI': 'Michigan', 'MN': 'Minnesota',
    'MS': 'Mississippi', 'MO': 'Missouri', 'MT': 'Montana', 'NE': 'Nebraska', 'NV': 'Nevada',
    'NH': 'New Hampshire', 'NJ': 'New Jersey', 'NM': 'New Mexico', 'NY': 'New York',
    'NC': 'North Carolina', 'ND': 'North Dakota', 'OH': 'Ohio', 'OK': 'Oklahoma', 'OR': 'Oregon',
    'PA': 'Pennsylvania', 'RI': 'Rhode Island', 'SC': 'South Carolina', 'SD': 'South Dakota',
    'TN': 'Tennessee', 'TX': 'Texas', 'UT': 'Utah', 'VT': 'Vermont', 'VA': 'Virginia',
    'WA': 'Washington', 'WV': 'West Virginia', 'WI': 'Wisconsin', 'WY': 'Wyoming',
}
_STATE_BY_NAME = {name.lower(): code for code, name in US_STATES.items()}

_CENSUS_SUFFIX = re.compile(
    r'\s+(city and borough|consolidated government|unified government|metropolitan government'
    r'|metro government|urban county|city|town|village|borough|cdp|municipality|plantation)$',
    re.I,
)

_ABBREVIATIONS = [
    (re.compile(r'^(st|ste)\.?\s+'), 'saint '),
    (re.compile(r'^ft\.?\s+'), 'fort '),
    (re.compile(r'^mt\.?\s+'), 'mount '),
]


def normalize_city(name: str) -> str:
    s = name.strip().lower()
    for pattern, repl in _ABBREVIATIONS:
        s = pattern.sub(repl, s)
    # dropping spaces too so "Mc Calla" == "McCalla"
    return re.sub(r'[^a-z0-9]', '', s)


def census_keys(census_name: str) -> tuple[str, set[str]]:
    """Main key for a Census place name plus looser aliases.

    Aliases cover names like "Augusta-Richmond County consolidated government (balance)"
    or "Boise City city", and should only be used if no other place has that key.
    """
    base = re.sub(r'\s*\(balance\)$', '', census_name.strip(), flags=re.I)
    base = re.sub(r'^town of\s+', '', base, flags=re.I)
    stripped = _CENSUS_SUFFIX.sub('', base)
    primary = normalize_city(stripped)
    variants = {stripped.split('-')[0].strip()}
    variants |= {_CENSUS_SUFFIX.sub('', v) for v in variants | {stripped}}
    aliases = {normalize_city(v) for v in variants if v} - {primary, ''}
    return primary, aliases


def parse_state(value: str) -> str | None:
    v = value.strip()
    if v.upper() in US_STATES:
        return v.upper()
    return _STATE_BY_NAME.get(v.lower())
