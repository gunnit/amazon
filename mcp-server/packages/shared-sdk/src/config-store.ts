import { chmodSync, existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";

import type { LocalState } from "./types.js";

const CONFIG_DIR = join(homedir(), ".inthezon");
const CONFIG_PATH = process.env.INTHEZON_CONFIG_PATH || join(CONFIG_DIR, "mcp-cli.json");
const DEFAULT_EXPORTS_DIR = join(CONFIG_DIR, "exports");

function defaultState(): LocalState {
  return {
    backendUrl: normalizeBackendUrl(process.env.INTHEZON_API_URL || "http://localhost:8000"),
  };
}

export function normalizeBackendUrl(url: string): string {
  return url.trim().replace(/\/+$/, "");
}

export function getConfigPath(): string {
  return CONFIG_PATH;
}

export function getDefaultExportsDir(): string {
  return process.env.INTHEZON_EXPORTS_DIR || DEFAULT_EXPORTS_DIR;
}

export function loadLocalState(): LocalState {
  if (!existsSync(CONFIG_PATH)) {
    return defaultState();
  }

  try {
    const raw = readFileSync(CONFIG_PATH, "utf8");
    const parsed = JSON.parse(raw) as LocalState;
    return {
      ...defaultState(),
      ...parsed,
      backendUrl: normalizeBackendUrl(parsed.backendUrl || defaultState().backendUrl),
    };
  } catch {
    return defaultState();
  }
}

export function saveLocalState(state: LocalState): LocalState {
  mkdirSync(dirname(CONFIG_PATH), { recursive: true });

  const normalized: LocalState = {
    ...state,
    backendUrl: normalizeBackendUrl(state.backendUrl),
  };

  const tempPath = `${CONFIG_PATH}.tmp`;
  writeFileSync(tempPath, `${JSON.stringify(normalized, null, 2)}\n`, "utf8");
  renameSync(tempPath, CONFIG_PATH);

  try {
    chmodSync(CONFIG_PATH, 0o600);
  } catch {
    // Best effort only.
  }

  return normalized;
}

export function clearLocalSession(): LocalState {
  const current = loadLocalState();
  return saveLocalState({
    backendUrl: current.backendUrl,
    exportsDir: current.exportsDir,
  });
}

export function setSelectedAccounts(accountIds: string[] | undefined): LocalState {
  const current = loadLocalState();
  return saveLocalState({
    ...current,
    selectedAccountIds: accountIds && accountIds.length > 0 ? accountIds : undefined,
  });
}

export function setExportsDir(path: string | undefined): LocalState {
  const current = loadLocalState();
  return saveLocalState({
    ...current,
    exportsDir: path && path.trim() ? path.trim() : undefined,
  });
}

export function resolveExportsDir(state?: LocalState): string {
  const s = state ?? loadLocalState();
  return s.exportsDir || getDefaultExportsDir();
}

export function ensureExportsDir(state?: LocalState): string {
  const dir = resolveExportsDir(state);
  mkdirSync(dir, { recursive: true });
  return dir;
}
