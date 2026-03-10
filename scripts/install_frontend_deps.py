import subprocess
import sys
import os

# Discover the correct frontend directory by searching sibling folders
candidates = [
    "/vercel/share/v0-next-shadcn/frontend",
    "/vercel/share/v0-project/frontend",
]

# Also search dynamically under /vercel/share
base = "/vercel/share"
for entry in os.listdir(base):
    p = os.path.join(base, entry, "frontend")
    if p not in candidates:
        candidates.append(p)

frontend_dir = None
for c in candidates:
    if os.path.isdir(c) and os.path.exists(os.path.join(c, "package.json")):
        frontend_dir = c
        break

if frontend_dir is None:
    print("ERROR: Could not find frontend directory under", base)
    sys.exit(1)
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
