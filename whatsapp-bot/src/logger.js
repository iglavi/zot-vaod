function ts() {
  return new Date().toISOString().replace("T", " ").slice(0, 19);
}

function line(level, args) {
  return [`[${ts()}] [${level}]`, ...args];
}

export const logger = {
  info: (...args) => console.log(...line("INFO", args)),
  warn: (...args) => console.warn(...line("WARN", args)),
  error: (...args) => console.error(...line("ERROR", args)),
  debug: (...args) => {
    if (process.env.LOG_LEVEL === "debug") console.log(...line("DEBUG", args));
  },
};
