from datetime import datetime
import urllib.parse
import re

def get_file_path(submission):
    """
    Derives the folder structure and filename for a submission.
    Returns: 'Daily Logs/YYYY/MonthName/{submission_id}.cpp'
    """
    creation_time = submission.get("creationTimeSeconds")
    dt = datetime.fromtimestamp(creation_time)
    year = dt.strftime("%Y")
    month = dt.strftime("%B")  # Full month name, e.g., "December"
    sub_id = submission.get("id")
    
    return f"Daily Logs/{year}/{month}/{sub_id}.cpp"

def make_readme_row(submission, file_path):
    """
    Formats a single submission as a Markdown table row.
    """
    creation_time = submission.get("creationTimeSeconds")
    dt = datetime.fromtimestamp(creation_time)
    date_str = dt.strftime("%b %d")  # e.g., "Dec 13"
    
    problem = submission.get("problem", {})
    rating = problem.get("rating", "-")
    title = problem.get("name", "Unknown Problem")
    contest_id = problem.get("contestId")
    index = problem.get("index")
    
    # Formulate problem URL
    if contest_id and index:
        problem_url = f"https://codeforces.com/problemset/problem/{contest_id}/{index}"
    else:
        problem_url = "#"
        
    # URL encode the file path for markdown link
    encoded_path = urllib.parse.quote(f"/{file_path}")
    filename = f"{submission.get('id')}.cpp"
    
    # Format tags/concepts
    tags = problem.get("tags", [])
    concepts = ", ".join(t.title() for t in tags) if tags else "Implementation"
    
    return f"| {date_str} | {rating} | [{title}]({problem_url}) | [`{filename}`]({encoded_path}) | {concepts} |"

def build_readme(existing_content, new_rows):
    """
    Appends new rows to the Markdown table in README.md.
    Looks for the table header and alignment row, finds the last consecutive table row,
    and inserts the new rows there. If not found, appends to the end.
    """
    if not existing_content.strip():
        # Fallback if empty
        header = "| Date | CF Rating | Problem | My Solution | Concepts |\n| :--- | ---: | :--- | :--- | :--- |\n"
        return header + "\n".join(new_rows) + "\n"
        
    lines = existing_content.splitlines()
    
    # Find table header
    header_idx = -1
    for i, line in enumerate(lines):
        if "CF Rating" in line and "My Solution" in line:
            header_idx = i
            break
            
    if header_idx == -1:
        # Table not found, append it to the end
        header = "\n| Date | CF Rating | Problem | My Solution | Concepts |\n| :--- | ---: | :--- | :--- | :--- |\n"
        return existing_content.rstrip() + "\n" + header + "\n".join(new_rows) + "\n"
        
    # Find the end of the table (consecutive lines starting with '|')
    last_table_idx = header_idx
    # Skip header and separator
    if last_table_idx + 1 < len(lines) and lines[last_table_idx + 1].strip().startswith("|"):
        last_table_idx += 1
        
    while last_table_idx + 1 < len(lines) and lines[last_table_idx + 1].strip().startswith("|"):
        last_table_idx += 1
        
    # Insert new rows after the last table line
    updated_lines = lines[:last_table_idx + 1] + new_rows + lines[last_table_idx + 1:]
    return "\n".join(updated_lines) + "\n"
