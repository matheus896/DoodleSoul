import subprocess
import sys
import os

frontend_dir = "/vercel/share/v0-project/frontend"
packages = ["react-router-dom", "lucide-react", "recharts"]

print(f"Installing packages in {frontend_dir}: {packages}")

result = subprocess.run(
    ["npm", "install"] + packages,
    cwd=frontend_dir,
    capture_output=True,
    text=True
)

print("STDOUT:", result.stdout)
print("STDERR:", result.stderr)
print("Return code:", result.returncode)

if result.returncode != 0:
    sys.exit(1)
else:
    print("Installation successful!")
