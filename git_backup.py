import os
import subprocess
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_git_command(command):
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        logger.info(f"Command output: {result.stdout}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed: {e.stderr}")
        return False

def backup_to_github():
    token = os.getenv('GITHUB_TOKEN')
    if not token:
        logger.error("GitHub token not found in environment")
        return False
    
    commands = [
        'git config --global user.email "replit@example.com"',
        'git config --global user.name "Replit Editor"',
        'git add .',
        'git commit -m "feat: implement payment callback with enhanced sheet validation"',
        'git tag -a "Got-the-Sheet-and-Row-to-Roundtrip-in-Stripe" -m "Payment callback implementation with Stripe metadata roundtrip. Current state: Identified discrepancy in row counting between Stripe metadata and Google Sheets."',
        f'git remote add origin-with-token https://{token}@github.com/AdamInOzzie/InstApps.git || git remote set-url origin-with-token https://{token}@github.com/AdamInOzzie/InstApps.git',
        'git push origin-with-token main --tags'
    ]
    
    for cmd in commands:
        if not run_git_command(cmd):
            return False
    return True

if __name__ == "__main__":
    backup_to_github()
