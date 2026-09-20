"""Clean and enrich a small CRM CSV using name matching and OpenAI."""

# this section imports all the modules needed for the program to run, including standard libraries and functions from the clean_crm module

import argparse #For parsing command-line arguments.
import csv      #For reading and writing CSV files.
import difflib  #For comparing sequences, used here for string similarity.
import json     #For working with JSON data.
import os       #For interacting with the operating system.
import re       #For regular expressions.
import string   #For string manipulation.

# This section names CRM columns and sets a default model. 
CRM_COLUMNS = ["Company", "Sector", "Short description"]
DEFAULT_MODEL = "gpt-4o-mini" 


#open the file, flag if cols or headers missing, strip whitespace, return list of dictionaries
def read_csv_file(file_path):
    """Read a CRM CSV and return records with the three expected columns."""
    try:
        #opens the CSV file for reading, using UTF-8 encoding and handling newlines appropriately
        with open(file_path, "r", newline="", encoding="utf-8-sig") as file:
            reader = csv.DictReader(file, strict=True)
            
            #check for header row
            if reader.fieldnames is None:
                raise ValueError("the CSV file has no header row")
            
            #check for company column
            if "Company" not in reader.fieldnames:
                raise ValueError("the CSV file must contain a Company column")

            #clean the records by trimming whitespace and ensuring all expected columns are present, even if they are empty
            records = []
            for row in reader:

                #new dict for each row, strip out spaces, make sure all cols there
                records.append({column: (row.get(column) or "").strip()
                                for column in CRM_COLUMNS})
            return records
    except (OSError, UnicodeError, csv.Error) as error:
        raise ValueError(f"could not read CSV file '{file_path}': {error}") from error


# this is basically the same as the read function above - it's just this puts the cleaned records into a new file 
def write_csv_file(file_path, records):
    """Write CRM records to a CSV with a stable column order."""
    try:
        #open the CSV file for writing, using UTF-8 encoding and handling newlines appropriately
        with open(file_path, "w", newline="", encoding="utf-8") as file:
        
            writer = csv.DictWriter(file, fieldnames=CRM_COLUMNS)
            writer.writeheader()
            #write the records to the CSV file, ensuring that each record has all expected columns, even if they are empty
            writer.writerows({column: record.get(column, "") for column in CRM_COLUMNS}
                             for record in records)
            
    except OSError as error:
        raise ValueError(f"could not write CSV file '{file_path}': {error}") from error


# lower cases and trims the company names
def normalize_company_name(company_name):
    """Make a company name easier to compare."""
    name = (company_name or "").lower().strip()

    #this replaces every punctuation character with a space
    name = name.translate(str.maketrans({character: " "
                                         for character in string.punctuation}))
    #r"\s+" is looking for instances of multiple spaces and removes and replaces with a single space                                     
    return re.sub(r"\s+", " ", name).strip()


# checks each new name against the CRM records and finds the best match and how strong that match is
# used later in process_user_records to determine whether to merge or add a new record
def find_strongest_match(company_name, crm_records):
    """Return the best CRM record and its SequenceMatcher score."""
   
    # draws the list of trimmed and lowercased name
    normalized_name = normalize_company_name(company_name)
    # defines the best match records
    strongest_record = None
    strongest_score = 0.0
    
    # this loop pulls up each record in the CRM and compares it to the new name, returning the best match and its score 
    for record in crm_records:
        # normalises each exisitng CRM name
        existing_name = normalize_company_name(record.get("Company", ""))
        if not existing_name:
            continue
        # returns a match score between 0 and 1, with no special rules
        score = difflib.SequenceMatcher(None, normalized_name, existing_name).ratio()
        #if the latest score is higher than the strongest score, store that
        if score > strongest_score:
            strongest_record = record
            strongest_score = score

    return strongest_record, strongest_score

# if a record in the user set is in CRM, use the non-blank user values to update the crm record
def merge_records(existing_record, user_record):
    """Update matched fields with non-empty values from a user record."""
    # this loop trims the user record, it replaces the existing value with a user supplied one
    for column in ("Sector", "Short description"):
        user_value = (user_record.get(column) or "").strip()
        if user_value:
            existing_record[column] = user_value
    return existing_record

# API issues
def add_warning(warnings, message):
    """Print and remember an API warning for the final summary."""
    warnings.append(message)
    print(f"Warning: {message}")


# this imports OpenAI if my API key is right 
def get_openai_client(api_key):
    """Create an OpenAI client, or return None when no key is available."""
    if not api_key:
        return None
    try:
        #this loads OpenAI
        from openai import OpenAI
        return OpenAI(api_key=api_key)
    except Exception:
        return None

# this defines the JSON request I'll go to an OpenAI model with
def get_json_response(client, model, prompt):
    """Ask the Responses API for JSON and return the decoded object."""
    response = client.responses.create(
        model=model,
        input=prompt,
        text={"format": {"type": "json_object"}},
    )
    return json.loads(response.output_text)

# this is the AI duplicate checking engine
def ask_openai_same_company(first_name, second_name, client, model, warnings):
    """Ask OpenAI whether two similar company names refer to one company."""
    if client is None:
        add_warning(warnings, "OPENAI_API_KEY is missing; ambiguous match was not merged")
        return None

    # this prompt sends pairs of companies to OpenAI
    prompt = (
        "Decide whether these two company names refer to the same company. "
        "Return only JSON in exactly this form: {\"same_company\": true}. "
        f"First name: {first_name}\nSecond name: {second_name}"
    )
    try:
        #converts JSON response into something python understands
        result = get_json_response(client, model, prompt)
        #if AI doesn't return the response in the right format, error and return result "same company" field
        if not isinstance(result, dict) or not isinstance(result.get("same_company"), bool):
            raise ValueError("JSON did not contain a boolean same_company field")
        return result["same_company"]

    except Exception as error:
        #if openAI fails
        add_warning(warnings, f"could not validate ambiguous match: {error}")
        return None

# asks for in sector and description if missing, using OpenAI
def ask_openai_for_missing_info(company_name, client, model, warnings):
    """Ask OpenAI for missing sector and description values."""
    if client is None:
        add_warning(warnings, f"OPENAI_API_KEY is missing; could not enrich {company_name}")
        return None

    # same structure as the previous prompt, but this one asks for sector and description

    prompt = (
        "Provide missing CRM information for this company. Return only JSON in exactly "
        "this form: {\"sector\": \"Technology\", "
        "\"short_description\": \"A concise factual description of the company.\"}. "
        "The short_description must be one sentence. "
        f"Company: {company_name}"
    )
    try:
        result = get_json_response(client, model, prompt)
        if not isinstance(result, dict):
            raise ValueError("JSON response was not an object")
        for column in ("sector", "short_description"):
            if result.get(column) is not None and not isinstance(result[column], str):
                raise ValueError(f"{column} must be text")
        return result
    except Exception as error:
        add_warning(warnings, f"could not enrich {company_name}: {error}")
        return None


# using AI, this only fills in the blanks in a record, it doesn't overwrite existing values
def enrich_record(record, client, model, warnings):
    """Fill only blank fields in one CRM record."""
    # checks for blanks in the sector and description fields 
    missing_sector = not record.get("Sector", "").strip()
    missing_description = not record.get("Short description", "").strip()
    if not missing_sector and not missing_description:
        return record

    # if either field is missing, it calls the OpenAI function to get the missing info
    result = ask_openai_for_missing_info(record["Company"], client, model, warnings)
    if result is None:
        return record
    if missing_sector and result.get("sector", "").strip():
        record["Sector"] = result["sector"].strip()
    if missing_description and result.get("short_description", "").strip():
        record["Short description"] = result["short_description"].strip()
    return record


# actually performes the matching, then merging or adding new records, then adding a sector and description if needed 
def process_user_records(crm_records, user_records, client, model):
    """Match, merge, add, and enrich user records in input order."""
    warnings = []
    # dictionary containing the summary values for the terminal output at the end of the run
    summary = {
        "user_records_processed": 0,
        "exact_matches": 0,
        "possible_matches_confirmed": 0,
        "possible_matches_new": 0,
        "genuinely_new": 0,
    }

    #loops through the user records to assign an action to each
    for user_record in user_records:
        summary["user_records_processed"] += 1
        # skips and warns if the company name is blank
        if not normalize_company_name(user_record.get("Company", "")):
            print("Warning: skipped a row with a blank company name")
            continue

        # calls function to find the best match in the CRM records for the current user record, returning the matching record and its score
        matching_record, score = find_strongest_match(user_record["Company"], crm_records)

        # if the match score is really low, the user record is probably new  - added as genuinely new 
        if matching_record is None or score < 0.5:
            record = {column: user_record.get(column, "").strip()
                      for column in CRM_COLUMNS}
            crm_records.append(record)
            summary["genuinely_new"] += 1
        # if the match score is perfect, the user record is merged into the existing CRM record
        elif score == 1.0:
            record = merge_records(matching_record, user_record)
            summary["exact_matches"] += 1
        else:
        # only bother AI if the match is a strong partial match
            same_company = ask_openai_same_company(
                user_record["Company"], matching_record["Company"],
                client, model, warnings
            )
            # if the AI believes there is a match then merge, otherwise treat record as new and add to CRM
            if same_company is True:
                record = merge_records(matching_record, user_record)
                summary["possible_matches_confirmed"] += 1
            else:
                record = {column: user_record.get(column, "").strip()
                          for column in CRM_COLUMNS}
                crm_records.append(record)
                summary["possible_matches_new"] += 1

        enrich_record(record, client, model, warnings)

    summary["api_warnings"] = len(warnings)
    return summary

# this provides the command line interface so user can enter the file names and paths for the CRM, user input, and output files
def parse_arguments():
    """Define the small command-line interface."""
    parser = argparse.ArgumentParser(description="Clean and enrich CRM company data")
    parser.add_argument("--crm", required=True, help="current CRM CSV file")
    parser.add_argument("--input", required=True, help="user company CSV file")
    parser.add_argument("--output", required=True, help="output CRM CSV file")
    return parser.parse_args()

# this takes the summary from process user records and prints it to the terminal, along with the output file path
def print_summary(summary, output_path):
    """Print the processing summary."""
    print("\nCRM cleaning complete")
    print(f"User records processed: {summary['user_records_processed']}")
    print(f"Exact matches: {summary['exact_matches']}")
    print(f"Possible matches confirmed by OpenAI: {summary['possible_matches_confirmed']}")
    print(f"Possible matches treated as new: {summary['possible_matches_new']}")
    print(f"Genuinely new companies: {summary['genuinely_new']}")
    print(f"API warnings: {summary['api_warnings']}")
    print(f"Output file: {output_path}")

# this is the master function that takes in the inputs, parses them, annd executes the program, calling the other functions as needed. It also handles errors and prints a summary at the end
def main():
    """Run the command-line program."""
    arguments = parse_arguments()

    try:
        # read the CRM and user CSV files, returning lists of dictionaries
        crm_records = read_csv_file(arguments.crm)
        user_records = read_csv_file(arguments.input)
        if not user_records:
            print("Warning: the user CSV is empty; nothing was processed")

        # draws the OpenAI model and API key from environment variables, defaulting to DEFAULT_MODEL if not set
        model = os.environ.get("OPENAI_MODEL", DEFAULT_MODEL)
        client = get_openai_client(os.environ.get("OPENAI_API_KEY"))
        summary = process_user_records(crm_records, user_records, client, model)
        # write the updated CRM records to the output CSV file and print a summary of the processing
        write_csv_file(arguments.output, crm_records)
        print_summary(summary, arguments.output)
    except ValueError as error:
        print(f"Error: {error}")
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()