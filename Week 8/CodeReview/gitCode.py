import git
import os
import sys
import time
import datetime
import chardet
import fnmatch
import shutil
import zipfile
from . import CodeReviewAI
import openai

# Define the cost per token and per second
COST_PER_TOKEN = 0.000002
COST_PER_SECOND = 0.005555

# Define the blacklist of file names
BLACKLIST = [
    "*.md", "changelog.txt", "*.txt", "*.ico", "README", "LICENSE",
    "*.csproj", "*.sln", ".git*", ".DS_Store", ".idea", ".vscode",
    "node_modules", "bower_components", "package-lock.json", "yarn.lock",
    "*file.js", "*config.js", "composer.*", "Gemfile*", "Procfile",
    ".travis.yml", ".gitlab-ci.yml", ".circleci", ".github", ".editorconfig",
    ".htaccess", ".htpasswd", "nginx.conf", "docker-compose.yml", "Jenkinsfile",
    "Makefile", ".mailmap", "*.png", "*.jpg", "*.jpeg", "*.gif", "*.bmp",
    "*.svg", "*.pdf", "*.zip", "*.tar", "*.gz", "*.exe", "*.dll", "*.so"
]

output_messages = []

def is_binary_file(file_path):
    """Check if a file is binary by its content."""
    try:
        with open(file_path, 'rb') as f:
            chunk = f.read(1024)
            if b'\x00' in chunk:  # Null bytes indicate binary file
                return True
            # Check if most characters are printable
            printable = sum(32 <= byte <= 126 or byte in (9, 10, 13) for byte in chunk)
            return (printable / len(chunk)) < 0.7
    except Exception:
        return True

def analyze_repository(repo_url):
    repo_name = repo_url.split("/")[-1].replace(".git", "")
    current_path = os.getcwd()
    local_repo_path = os.path.join(current_path, repo_name)

    if os.path.isdir(local_repo_path):
        try:
            repo = git.Repo(local_repo_path)
            origin = repo.remote(name='origin')
            origin.pull()
            output_messages.append(f"Repository successfully updated: {repo_url} --> {local_repo_path}")
        except Exception as e:
            output_messages.append(f"Error updating repository: {e}")
            sys.exit(1)
    else:
        try:
            git.Repo.clone_from(repo_url, local_repo_path)
            output_messages.append(f"Cloning is successful: {repo_url} --> {local_repo_path}")
        except git.exc.GitCommandError as e:
            output_messages.append(f"An error occurred while cloning the repository: {e}")
            sys.exit(1)

    analyze_files(local_repo_path)
    try:
        shutil.rmtree(local_repo_path)  # Clean up the cloned repository
    except Exception as e:
        output_messages.append(f"Warning: Could not clean up repository: {e}")

def analyze_local_path(local_path):
    if local_path.endswith('.zip'):
        repo_name = os.path.basename(local_path).replace('.zip', '')
        extract_path = os.path.join(os.getcwd(), repo_name)
        try:
            with zipfile.ZipFile(local_path, 'r') as zip_ref:
                zip_ref.extractall(extract_path)
            analyze_files(extract_path)
            shutil.rmtree(extract_path)  # Clean up the extracted files
        except Exception as e:
            output_messages.append(f"Error processing zip file: {e}")
            sys.exit(1)
    elif os.path.isdir(local_path):
        analyze_files(local_path)
    else:
        output_messages.append(f"Invalid path: {local_path}")
        sys.exit(1)

def analyze_files(path):
    current_path = os.getcwd()
    repo_name = os.path.basename(path)
    report_dir = os.path.join(current_path, 'report', repo_name)

    if not os.path.exists(report_dir):
        os.makedirs(report_dir)

    blacklist = [item.lower() for item in BLACKLIST]

    for root, _, files in os.walk(path):
        for file in files:
            file_path = os.path.join(root, file)
            
            # Skip blacklisted and binary files
            if (any(fnmatch.fnmatch(file.lower(), pattern) for pattern in blacklist) or
                is_binary_file(file_path)):
                output_messages.append(f"Excluding file: {file_path}")
                continue
            
            try:
                # Read file with encoding detection
                with open(file_path, 'rb') as f:
                    file_contents = f.read()

                # Detect encoding and decode
                try:
                    detected_encoding = chardet.detect(file_contents)['encoding']
                    file_contents = file_contents.decode(detected_encoding or 'utf-8', errors='replace')
                except UnicodeDecodeError as e:
                    output_messages.append(f"Could not decode {file_path}: {e}")
                    continue

                # Analyze file contents
                start_time = time.time()
                analysis = CodeReviewAI.analyze_file_contents(file_contents, file_path)

                if analysis is None:
                    continue

                # Generate report
                now = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                report_file_path = os.path.join(report_dir, f'{repo_name}-{now}.md')
                
                with open(report_file_path, 'a', encoding='utf-8') as reporting:
                    original_stdout = sys.stdout
                    sys.stdout = reporting
                    
                    try:
                        end_time = time.time()
                        time_consumed = end_time - start_time
                        num_seconds = time_consumed
                        
                        num_tokens = int(analysis['usage']['total_tokens'])
                        token_cost = num_tokens * COST_PER_TOKEN
                        time_cost = num_seconds * COST_PER_SECOND
                        total_cost = token_cost + time_cost
                        
                        print(f"### Total time consumed: {time_consumed:.2f} seconds")
                        print(f"### Total tokens used: {num_tokens}")
                        print(f"### Total cost is: ${total_cost:.2f}")
                        print(f"### File: {file_path}")
                        print(f'{analysis["choices"][0]["message"]["content"]}\n\n\n')
                        
                        output_messages.append(f"Analyzed {file_path}")
                    finally:
                        sys.stdout = original_stdout

            except KeyboardInterrupt:
                print("\nAnalysis interrupted by user. Exiting...")
                sys.exit()
            except Exception as e:
                output_messages.append(f"Error analyzing {file_path}: {e}")
                continue