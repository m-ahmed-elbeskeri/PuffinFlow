# sdk/plugin_installer.py

"""Plugin installation utility for FlowForge."""

import os
import sys
import requests
import zipfile
import tempfile
import shutil
import subprocess
from pathlib import Path

def install_from_github(repo: str, target_dir: str) -> bool:
    """Install a plugin from a GitHub repository."""
    print(f"Installing plugin from GitHub: {repo}")
    
    # Download the repository
    url = f"https://github.com/{repo}/archive/refs/heads/main.zip"
    response = requests.get(url, stream=True)
    
    if response.status_code == 404:
        # Try master branch if main not found
        url = f"https://github.com/{repo}/archive/refs/heads/master.zip"
        response = requests.get(url, stream=True)
    
    if response.status_code != 200:
        print(f"Error: Could not download repository: {response.status_code}")
        return False
    
    # Extract to temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        zip_path = os.path.join(temp_dir, "repo.zip")
        with open(zip_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        # Unzip
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
        
        # Find the plugin directory
        extracted_dirs = [d for d in os.listdir(temp_dir) 
                         if os.path.isdir(os.path.join(temp_dir, d))]
        if not extracted_dirs:
            print("Error: No directories found in repository")
            return False
        
        repo_dir = os.path.join(temp_dir, extracted_dirs[0])
        
        # Look for manifest.yaml
        manifest_path = os.path.join(repo_dir, "manifest.yaml")
        if not os.path.exists(manifest_path):
            print("Error: No manifest.yaml found in repository")
            return False
        
        # Determine plugin name from repository
        plugin_name = repo.split("/")[-1]
        if plugin_name.startswith("flowforge-plugin-"):
            plugin_name = plugin_name[len("flowforge-plugin-"):]
        
        # Create target directory
        plugin_dir = os.path.join(target_dir, plugin_name)
        if os.path.exists(plugin_dir):
            print(f"Warning: Plugin directory already exists: {plugin_dir}")
            print("Removing existing plugin...")
            shutil.rmtree(plugin_dir)
        
        # Copy files
        shutil.copytree(repo_dir, plugin_dir)
        print(f"Plugin installed to: {plugin_dir}")
        
        # Install requirements if any
        req_path = os.path.join(plugin_dir, "requirements.txt")
        if os.path.exists(req_path):
            print("Installing plugin requirements...")
            try:
                subprocess.check_call([sys.executable, "-m", "pip", 
                                      "install", "-r", req_path])
                print("Requirements installed successfully")
            except subprocess.CalledProcessError as e:
                print(f"Warning: Failed to install requirements: {e}")
        
        return True