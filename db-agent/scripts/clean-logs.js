#!/usr/bin/env node
const fs = require("fs");
const path = require("path");

const logsRoot = path.resolve(__dirname, "..", "logs");
if (!fs.existsSync(logsRoot)) {
  console.log("No logs directory.");
  process.exit(0);
}

let removed = 0;
for (const entry of fs.readdirSync(logsRoot, { withFileTypes: true })) {
  if (entry.name === "README.md") continue;
  const full = path.join(logsRoot, entry.name);
  if (entry.isDirectory()) {
    fs.rmSync(full, { recursive: true, force: true });
    removed += 1;
  } else if (entry.isFile()) {
    fs.unlinkSync(full);
    removed += 1;
  }
}
console.log(`Cleaned logs under ${logsRoot} (${removed} entries removed). README.md kept.`);
