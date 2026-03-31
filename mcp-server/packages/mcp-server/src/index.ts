#!/usr/bin/env node

import { fileURLToPath } from "node:url";

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";

import { registerInthezonTools } from "./tools.js";

export async function startMcpServer(): Promise<void> {
  const server = new McpServer({
    name: "inthezon",
    version: "0.1.0",
  });

  registerInthezonTools(server);

  const transport = new StdioServerTransport();
  await server.connect(transport);
}

const launchedDirectly = process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];

if (launchedDirectly) {
  startMcpServer().catch((error) => {
    console.error("[inthezon-mcp-server] Failed to start:", error);
    process.exit(1);
  });
}
