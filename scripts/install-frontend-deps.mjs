import { execSync } from "child_process";
import { resolve } from "path";

const cwd = resolve("/vercel/share/v0-project/frontend");

console.log("[v0] Installing frontend dependencies in:", cwd);

try {
  execSync("npm install react-router-dom lucide-react recharts", {
    cwd,
    stdio: "inherit",
  });
  console.log("[v0] Dependencies installed successfully.");
} catch (err) {
  console.error("[v0] Install failed:", err.message);
  process.exit(1);
}
