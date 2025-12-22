# J2J Converter v327

Converts JPK files (Jitterbit Design Studio) to JSON format (Jitterbit Integration Studio).

## Requirements

- Python 3.10+
- No external dependencies (uses standard library only)

## Usage

```bash
python j2j_v327.py <jpk_file> <output_file> [config_file]
```

### Arguments

| Argument | Description |
|----------|-------------|
| `jpk_file` | Path to JPK file to convert |
| `output_file` | Path for output JSON file |
| `config_file` | Optional: Path to configuration file (default: `j2j_config.json`) |

### Examples

```bash
# Basic conversion
python j2j_v327.py my_project.jpk output.json

# With custom config
python j2j_v327.py my_project.jpk output.json custom_config.json

# Verbose output
python j2j_v327.py my_project.jpk output.json -v
```

## Project Structure

```
j2j_v3_converter/
├── j2j_v327.py                 # Main entry point
├── jpk_discover_transformations.py  # JPK analysis tool
├── j2j_config.json             # Default configuration
├── config/
│   └── output_v139_woocommerce_free.json  # Baseline validation
├── schema_references/          # Reference schemas for conversion
│   ├── jb-canonical-contact.json
│   ├── salesforce_Query_output_*.json
│   ├── netsuite_Upsert_*.json
│   └── ...
└── j2j/                        # Core package
    ├── config/                 # Configuration management
    ├── converters/             # JPK to JSON conversion logic
    ├── generators/             # Component factories
    ├── parsers/                # JPK, XML, XSD parsing
    └── utils/                  # Utilities and exceptions
```

## Discovery Tool

Analyze JPK contents without conversion:

```bash
python jpk_discover_transformations.py <jpk_file>
```

## Output

The converter generates a JSON file compatible with Jitterbit Integration Studio import.

Components converted:
- Project Variables (Type 1000)
- Global Variables (Type 1300)
- Scripts (Type 400)
- Endpoints (Type 500/600)
- Transformations (Type 700)
- Operations (Type 200)
- Schema Documents (Type 900)
- XSD Assets

## Configuration

Edit `j2j_config.json` to customize:
- Baseline validation file path
- Schema reference locations
- Trace logging options
- Transformation rules

## Tested Projects

| Project | Components | Status |
|---------|------------|--------|
| VC (Salesforce to NetSuite) | 125 | Deployed |
| VB2_1 (Salesforce to NetSuite, multi-activity) | 135 | Deployed |

## Changelog

### 2024-12-22
- **Fix:** Removed aggressive Type 600 deduplication that broke multi-activity projects
- **Fix:** Use proper adapter display names (NetSuite vs Netsuite)
- **Fix:** Filter PRESCRIPT nodes from schema documents
- **Fix:** Skip Salesforce non-query response origin updates
- **Fix:** Deduplicate Type 600s against baseline only (not during extraction)
- **Enhancement:** JPK Document flat fields priority for schema extraction

See `docs/investigations_standalone.md` for detailed rule documentation.
