import os
import json
import argparse
from datetime import datetime
from mcp import StdioServerParameters
from google.adk.agents import Agent
from google.adk.models import Gemini
from google.adk.tools import McpToolset
import google.auth

# Import local modules
import cf_fetcher
import file_manager
import github_manager

class SimpleAgentRunner:
    def __init__(self, agent):
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService
        
        self.session_service = InMemorySessionService()
        self.session = self.session_service.create_session_sync(user_id="user", app_name="hurdler")
        self.runner = Runner(agent=agent, session_service=self.session_service, app_name="hurdler")
        
    def chat(self, text: str) -> str:
        from google.adk.agents.run_config import RunConfig, StreamingMode
        from google.genai import types
        
        message = types.Content(
            role="user", parts=[types.Part.from_text(text=text)]
        )
        events = list(
            self.runner.run(
                new_message=message,
                user_id="user",
                session_id=self.session.id,
                run_config=RunConfig(streaming_mode=StreamingMode.NONE),
            )
        )
        
        response_parts = []
        for event in events:
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        response_parts.append(part.text)
        return "".join(response_parts)

def load_pat_from_config(workspace_dir):
    config_path = os.path.join(workspace_dir, ".agents", "mcp_config.json")
    if not os.path.exists(config_path):
        return None
        
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        
        github_cfg = config.get("mcpServers", {}).get("github", {})
        env = github_cfg.get("env", {})
        pat = env.get("GITHUB_PERSONAL_ACCESS_TOKEN")
        if pat and pat != "YOUR_GITHUB_PERSONAL_ACCESS_TOKEN_HERE":
            return pat
    except Exception as e:
        print(f"Error reading mcp_config.json: {e}")
        
    return None

def main():
    parser = argparse.ArgumentParser(description="Codeforces Solutions Tracker Agent")
    parser.add_argument("--username", required=True, help="Codeforces handle")
    parser.add_argument("--owner", required=True, help="GitHub repository owner")
    parser.add_argument("--repo", required=True, help="GitHub repository name")
    args = parser.parse_args()

    workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    state_path = os.path.join(workspace_dir, "state.json")
    readme_path = os.path.join(workspace_dir, "README.md")
    cookies_path = os.path.join(workspace_dir, ".agents", "cookies.json")

    # 1. Load GitHub Personal Access Token
    pat = load_pat_from_config(workspace_dir)
    if not pat:
        pat = os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN")
        
    if not pat:
        print("Error: GitHub Personal Access Token (PAT) not found.")
        print("Please set it in .agents/mcp_config.json or as GITHUB_PERSONAL_ACCESS_TOKEN environment variable.")
        return

    # 2. Load or initialize local state
    if os.path.exists(state_path):
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    else:
        state = {
            "last_submission_id": None,
            "pending_files": [],
            "pending_count": 0
        }

    # 3. Setup Google ADK environment & credentials
    try:
        _, project_id = google.auth.default()
        os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
        os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
    except Exception as e:
        print(f"Warning: Could not configure default Google Cloud credentials automatically: {e}")

    # 4. Initialize GitHub MCP toolset
    print("Starting GitHub MCP server...")
    mcp_toolset = McpToolset(
        connection_params=StdioServerParameters(
            command="docker",
            args=[
                "run", "-i", "--rm",
                "-e", "GITHUB_PERSONAL_ACCESS_TOKEN",
                "ghcr.io/github/github-mcp-server"
            ],
            env={
                "GITHUB_PERSONAL_ACCESS_TOKEN": pat
            }
        )
    )

    # 5. Initialize the Agent & Runner
    agent = Agent(
        name="github_agent",
        model=Gemini(model="gemini-3.5-flash"),
        instruction="You are a helper agent that interfaces with GitHub repositories using the GitHub MCP server.",
        tools=[mcp_toolset]
    )
    runner = SimpleAgentRunner(agent)

    # 6. Commit previous changes if any pending files exist
    if state["pending_count"] > 0:
        print(f"Found {state['pending_count']} pending submissions from the last run.")
        print("Ensuring GitHub repository is set up...")
        
        # Ensure repository exists
        if not github_manager.create_repo(runner, args.owner, args.repo):
            print("Failed to ensure GitHub repository setup. Exiting.")
            return
            
        print("Creating commit batch for GitHub...")
        batch_files = []
        
        # Add all pending source code files
        for rel_path in state["pending_files"]:
            full_path = os.path.join(workspace_dir, rel_path)
            if os.path.exists(full_path):
                with open(full_path, "r", encoding="utf-8") as f:
                    content = f.read()
                batch_files.append({"path": rel_path, "content": content})
            else:
                print(f"Warning: Pending file {rel_path} was not found on local disk. Skipping.")

        # Add updated README.md
        if os.path.exists(readme_path):
            with open(readme_path, "r", encoding="utf-8") as f:
                readme_content = f.read()
            batch_files.append({"path": "README.md", "content": readme_content})

        # Add the reset state.json to the push batch
        new_state = {
            "last_submission_id": state["last_submission_id"],
            "pending_files": [],
            "pending_count": 0
        }
        batch_files.append({"path": "state.json", "content": json.dumps(new_state, indent=2)})

        commit_msg = f"{state['pending_count']}x Codeforces"
        print(f"Pushing commit: '{commit_msg}' to GitHub...")
        if github_manager.push_batch(runner, args.owner, args.repo, batch_files, commit_msg):
            print("Successfully pushed changes to GitHub!")
            state = new_state
            with open(state_path, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
        else:
            print("Failed to push changes to GitHub. Keeping local files as pending.")
            return

    # 7. Fetch new submissions from Codeforces API
    print(f"Fetching accepted submissions for Codeforces user '{args.username}'...")
    try:
        new_subs = cf_fetcher.fetch_accepted(args.username, after_id=state["last_submission_id"])
    except Exception as e:
        print(f"Error fetching submissions from Codeforces: {e}")
        return

    if not new_subs:
        print("No new accepted submissions found.")
        return

    print(f"Found {len(new_subs)} new accepted submissions.")
    new_rows = []
    
    # Start the browser scraper
    scraper = cf_fetcher.CodeforcesScraper(cookies_path)
    scraper.start()
    
    try:
        # Process each new submission
        for idx, sub in enumerate(new_subs):
            sub_id = sub["id"]
            contest_id = sub.get("contestId")
            prob_name = sub.get("problem", {}).get("name", "Problem")
            print(f"[{idx + 1}/{len(new_subs)}] Scraping code for '{prob_name}' (ID: {sub_id})...")
            
            try:
                # Scrape source code from webpage
                code = scraper.get_code(contest_id, sub_id)
                
                # Save file locally
                file_path = file_manager.get_file_path(sub)
                full_file_path = os.path.join(workspace_dir, file_path)
                
                os.makedirs(os.path.dirname(full_file_path), exist_ok=True)
                with open(full_file_path, "w", encoding="utf-8") as f:
                    f.write(code)
                    
                # Create row for README
                row = file_manager.make_readme_row(sub, file_path)
                new_rows.append(row)
                
                # Track pending file path
                state["pending_files"].append(file_path)
                state["pending_count"] += 1
                state["last_submission_id"] = max(state["last_submission_id"] or 0, sub_id)
                
            except Exception as e:
                print(f"Error processing submission {sub_id}: {e}")
                # Keep state updated up to this point and stop to avoid errors piling up
                break
    finally:
        # Stop Chrome driver
        scraper.stop()

    # 8. Update local README.md and state.json
    if new_rows:
        print("Updating local README.md...")
        existing_readme = ""
        if os.path.exists(readme_path):
            with open(readme_path, "r", encoding="utf-8") as f:
                existing_readme = f.read()
                
        updated_readme = file_manager.build_readme(existing_readme, new_rows)
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(updated_readme)

        print("Saving local state.json...")
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
            
        print(f"Processed {len(new_rows)} new submissions locally.")
        print(f"Total pending submissions to commit next run: {state['pending_count']}")

if __name__ == "__main__":
    main()
