import json
import re

def create_repo(runner, owner, repo, description="Codeforces solutions tracker"):
    """
    Creates a new GitHub repository using the GitHub MCP server.
    """
    prompt = (
        f"Use the github MCP server's create_repository tool to create a repository. "
        f"Parameters: name='{repo}', description='{description}', private=true. "
        f"If the repository already exists or is created successfully, output exactly 'REPO_READY'. "
        f"Otherwise, output the detailed error."
    )
    
    text = runner.chat(prompt)
    
    if "REPO_READY" in text or "already exists" in text.lower():
        return True
    
    print(f"[github_manager] Repository setup output: {text}")
    return False

def read_state(runner, owner, repo):
    """
    Reads the state.json file from the GitHub repository.
    Returns the parsed JSON dictionary, or None if the file doesn't exist.
    """
    prompt = (
        f"Use the github MCP server's get_file_contents tool to read 'state.json' from the repository '{repo}' "
        f"owned by '{owner}' on the 'main' branch. "
        f"If the file is successfully read, print its raw text contents inside a markdown code block. "
        f"If you encounter a 404 error, the file doesn't exist, or any error indicates the file is missing, "
        f"reply with exactly 'FILE_NOT_FOUND'."
    )
    
    text = runner.chat(prompt)
    
    if "FILE_NOT_FOUND" in text or "404" in text:
        return None
        
    # Extract JSON block
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if not match:
        # Fallback to general JSON-like pattern
        match = re.search(r"(\{.*?\})", text, re.DOTALL)
        
    if match:
        try:
            return json.loads(match.group(1))
        except Exception as e:
            print(f"[github_manager] Failed to parse JSON from response: {e}. Raw text was:\n{text}")
            
    return None

def read_readme(runner, owner, repo):
    """
    Reads the README.md file from the GitHub repository.
    Returns the file content as a string, or None if the file doesn't exist.
    """
    prompt = (
        f"Use the github MCP server's get_file_contents tool to read 'README.md' from the repository '{repo}' "
        f"owned by '{owner}' on the 'main' branch. "
        f"Output the raw text contents of README.md inside a markdown code block. "
        f"If you get a 404 error or the file does not exist, reply with exactly 'FILE_NOT_FOUND'."
    )
    
    text = runner.chat(prompt)
    
    if "FILE_NOT_FOUND" in text or "404" in text:
        return None
        
    # Extract code block content
    match = re.search(r"```(?:markdown|text)?\n(.*?)\n```", text, re.DOTALL)
    if match:
        return match.group(1)
        
    return text

def push_batch(runner, owner, repo, files, message):
    """
    Pushes multiple files to the GitHub repository in a single commit using push_files.
    files: List of dicts, e.g., [{"path": "Daily Logs/...", "content": "..."}]
    """
    # Structure files argument as JSON to be passed cleanly
    files_json = json.dumps(files)
    
    prompt = (
        f"Use the github MCP server's push_files tool to push the following files to repository '{repo}' "
        f"owned by '{owner}' on the 'main' branch. "
        f"Commit message: '{message}'.\n\n"
        f"Files to push:\n{files_json}\n\n"
        f"If the push is successful, reply with exactly 'PUSH_SUCCESSFUL'. "
        f"Otherwise, output the detailed error message."
    )
    
    text = runner.chat(prompt)
    
    if "PUSH_SUCCESSFUL" in text:
        return True
        
    print(f"[github_manager] Push failed. Output:\n{text}")
    return False
