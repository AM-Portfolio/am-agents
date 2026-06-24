/**
 * Tee stdout/stderr to logs/<scope>/<timestamp>_<npm-script>.log
 * Same pattern as am-platform/automation/scripts/run-with-logs.js
 */
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");

const serviceRoot = path.resolve(__dirname, "..");
const logsRoot = path.join(serviceRoot, "logs");
const LOG_TZ = "Asia/Kolkata";

function istParts(date) {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: LOG_TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).formatToParts(date);
  const pick = (type) => parts.find((p) => p.type === type)?.value ?? "";
  return {
    year: pick("year"),
    month: pick("month"),
    day: pick("day"),
    hour: pick("hour"),
    minute: pick("minute"),
    second: pick("second"),
  };
}

function formatIstStamp(date) {
  const p = istParts(date);
  return `${p.year}-${p.month}-${p.day}_${p.hour}-${p.minute}-${p.second}`;
}

function formatIstIso(date) {
  const p = istParts(date);
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}:${p.second}+05:30`;
}

const rawArgs = process.argv.slice(2);
if (rawArgs.length === 0) {
  console.error("Usage: node scripts/run-with-logs.js <command> [args...]");
  process.exit(1);
}

function logScope() {
  const pkg = process.env.npm_package_name || "";
  if (pkg.startsWith("@am/")) {
    return pkg.replace("@am/", "");
  }
  return "db-agent";
}

const scope = logScope();
const scriptName = (process.env.npm_lifecycle_event || "command").replace(/:/g, "-");
const startedAt = new Date();
const stamp = formatIstStamp(startedAt);

const scopeDir = path.join(logsRoot, scope);
fs.mkdirSync(scopeDir, { recursive: true });

const logFile = path.join(scopeDir, `${stamp}_${scriptName}.log`);
const logStream = fs.createWriteStream(logFile, { flags: "w" });

function writeLine(line, targetStdout = true) {
  const text = line.endsWith("\n") ? line : `${line}\n`;
  logStream.write(text);
  if (targetStdout) {
    process.stdout.write(text);
  } else {
    process.stderr.write(text);
  }
}

writeLine(`=== ${formatIstIso(startedAt)} | npm: ${process.env.npm_lifecycle_event || "(direct)"} ===`);
writeLine(`=== package: ${process.env.npm_package_name || "(none)"} ===`);
writeLine(`=== log file: ${logFile} ===`);
writeLine(`=== cwd: ${process.cwd()} ===`);
writeLine(`=== command: ${rawArgs.join(" ")} ===`);
writeLine("");

console.log(`[run-with-logs] ${scope}/${path.basename(logFile)}`);

const child = spawn(rawArgs.join(" "), {
  cwd: process.cwd(),
  env: process.env,
  shell: true,
  stdio: ["inherit", "pipe", "pipe"],
});

child.stdout.on("data", (chunk) => {
  logStream.write(chunk);
  process.stdout.write(chunk);
});

child.stderr.on("data", (chunk) => {
  logStream.write(chunk);
  process.stderr.write(chunk);
});

child.on("error", (err) => {
  writeLine(`[run-with-logs] Failed to start process: ${err.message}`, false);
  logStream.end(() => process.exit(1));
});

child.on("close", (code, signal) => {
  const endedAt = new Date();
  const footer = [
    "",
    `=== ${formatIstIso(endedAt)} | exit code: ${code ?? "null"}${signal ? ` | signal: ${signal}` : ""} ===`,
  ].join("\n");
  logStream.write(`${footer}\n`);
  console.log(`[run-with-logs] Finished (exit ${code ?? "null"}). Log: ${logFile}`);
  logStream.end(() => process.exit(code === 0 ? 0 : code ?? 1));
});
