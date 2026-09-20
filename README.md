# CRM Data-Cleaning Tool

This small Python 3 command-line program combines a current CRM CSV with a user
CSV. It finds likely company matches, keeps useful non-empty information, and
asks OpenAI to resolve uncertain names or fill missing company details.

The program is intentionally made from straightforward functions, dictionaries,
loops, and Python's standard library. It does not use a web framework, pandas,
JavaScript, HTML, CSS, or Streamlit.

## File structure

```text
clean_crm.py                Main program and command-line interface
test_clean_crm.py           Offline unittest tests
requirements.txt            The official OpenAI Python package
sample_user_companies.csv   Small example input
companies_100(1).csv        Existing CRM file supplied separately
user_companies.csv          Your input file supplied separately
cleaned_crm.csv             Generated output file
```

## Setup

Create a virtual environment from the project folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Set the API key in the same terminal. Never put the key in this repository:

```bash
export OPENAI_API_KEY="your-api-key"
export OPENAI_MODEL="gpt-4o-mini"
```

`OPENAI_MODEL` is optional. The program uses `gpt-4o-mini` when it is not set.

## Run it

```bash
python clean_crm.py \
  --crm 'companies_100(1).csv' \
  --input user_companies.csv \
  --output cleaned_crm.csv
```

The CRM and user files must contain a `Company` column. `Sector` and `Short
description` are optional in the user file; missing values are treated as blank.
The output always contains these three columns:

```text
Company,Sector,Short description
Acme Inc,Technology,A software company.
Northwind Rail,Transport,A regional rail operator.
```

## Matching logic

Before comparing names, the program lowercases them, trims the edges, replaces
simple punctuation with spaces, and collapses repeated spaces. For example,
`"  Acme, Inc. "` becomes `"acme inc"`.

`difflib.SequenceMatcher` returns a similarity ratio from `0.0` to `1.0`. The
program compares a user company with every current CRM company and keeps the
strongest score:

- `1.0`: exact normalized match. Merge immediately and do not call OpenAI.
- `0.5` through less than `1.0`: possible match. Ask OpenAI for JSON containing
  `{"same_company": true}` or `false`.
- Below `0.5`: treat the company as new without asking OpenAI.

Exact matching is deterministic and does not need an external opinion. This is
faster, cheaper, and avoids an unnecessary API call. When OpenAI rejects an
ambiguous match, returns invalid JSON, or cannot be reached, the program treats
the user company as new and prints a warning.

After matching or adding a company, OpenAI may be asked for missing `Sector` or
`Short description` values. It receives a JSON response request with both
fields, but the program fills only fields that are currently blank. It never
overwrites non-empty enrichment values. Enrichment failures leave fields blank.

The in-memory CRM is updated after every user row. Therefore, a later row can
match a company that was added earlier in the same run.

## Tests

The tests use only Python's built-in `unittest` module and fake API responses:

```bash
python -m unittest -v
```

They cover normalization, strongest-match selection, threshold behavior, safe
merging, and filling only blank fields. No real OpenAI API calls are made.

## Error handling and limitations

The program reports missing files, malformed or missing CSV headers, blank user
company names, an empty user CSV, missing API keys, API failures, and invalid
JSON. It writes the output only after processing finishes successfully.

This is a deliberately small cleaning tool, not a complete entity-resolution
system. Similarity scores can be misleading for short or common names. OpenAI
can also make a wrong judgment, so ambiguous merges should be reviewed for
important CRM data. The program does not deduplicate the original CRM file or
validate whether an AI-generated description is factually correct.

## Interview questions and simple answers

1. **Why normalize names before comparing them?**  It removes harmless format
   differences such as capitalization, punctuation, and extra spaces.
2. **Why use `SequenceMatcher`?**  It is built into Python and gives a simple
   explainable similarity score without another dependency.
3. **Why is an exact score handled without OpenAI?**  A normalized score of
   `1.0` is a deterministic match, so an API call would add cost and delay.
4. **What happens when OpenAI fails?**  The program prints a warning. An
   ambiguous match is kept as a new company, and a missing field stays blank.
5. **How do you avoid losing CRM data?**  Blank user values never replace
   existing values, and enrichment writes only into fields that are blank.# investec-quant-strats
test projects for tomorrow
