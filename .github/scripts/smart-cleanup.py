import os
import requests
from datetime import datetime

# Environment Variables
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
ORG_NAME = "AM-Portfolio"
REPO_NAME = "am-agents"
MAIN_KEEP = 5
FEATURE_KEEP = 5

PACKAGES = [
    "am-fin-agent",
    "am-support-agent",
    "am-tool-agent",
    "am-ui-test-agent",
    "am-db-agent"
]

HEADERS = {
    "Accept": "application/vnd.github+json",
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "X-GitHub-Api-Version": "2022-11-28"
}

def get_package_versions(package_name):
    url = f"https://api.github.com/orgs/{ORG_NAME}/packages/container/{package_name}/versions"
    response = requests.get(url, headers=HEADERS, params={"per_page": 100})
    if response.status_code == 404:
        return []
    response.raise_for_status()
    return response.json()

def get_run_branch(run_id):
    url = f"https://api.github.com/repos/{ORG_NAME}/{REPO_NAME}/actions/runs/{run_id}"
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        return response.json().get('head_branch')
    return None

def delete_version(package_name, version_id):
    url = f"https://api.github.com/orgs/{ORG_NAME}/packages/container/{package_name}/versions/{version_id}"
    response = requests.delete(url, headers=HEADERS)
    if response.status_code == 204:
        print(f"Successfully deleted version {version_id} from {package_name}")
    else:
        print(f"Failed to delete {version_id}: {response.status_code} - {response.text}")

def clean_package(package_name):
    print(f"\n--- Cleaning package: {package_name} ---")
    versions = get_package_versions(package_name)
    if not versions:
        print("No versions found or package doesn't exist.")
        return
        
    versions.sort(key=lambda x: x['created_at'], reverse=True)
    
    main_versions = []
    feature_versions = []
    other_versions = []
    
    print(f"Total versions found: {len(versions)}")

    for v in versions:
        version_id = v['id']
        tags = v['metadata']['container']['tags']
        
        if 'latest' in tags:
            print(f"Keeping version {version_id} (tagged as latest)")
            continue
            
        run_tag = None
        for tag in tags:
            if tag.isdigit():
                run_tag = tag
                break
                
        if run_tag:
            branch = get_run_branch(run_tag)
            if branch == 'main' or branch == 'master':
                main_versions.append(v)
            else:
                feature_versions.append(v)
        else:
            other_versions.append(v)
            
    print(f"Found {len(main_versions)} main builds, {len(feature_versions)} feature builds.")
    
    to_delete = []
    
    if len(main_versions) > MAIN_KEEP:
        to_delete.extend(main_versions[MAIN_KEEP:])
    if len(feature_versions) > FEATURE_KEEP:
        to_delete.extend(feature_versions[FEATURE_KEEP:])
        
    to_delete.extend(other_versions) 
    
    if not to_delete:
        print("Nothing to clean up! Exiting.")
        return

    print(f"Proceeding to delete {len(to_delete)} old versions...")
    for v in to_delete:
        print(f"Deleting version {v['id']} created at {v['created_at']}")
        delete_version(package_name, v['id'])

def main():
    if not GITHUB_TOKEN:
        print("Missing GITHUB_TOKEN!")
        exit(1)

    for pkg in PACKAGES:
        clean_package(pkg)

if __name__ == "__main__":
    main()
