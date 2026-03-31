#!/usr/bin/env node

import {
  confirm,
  intro,
  isCancel,
  note,
  outro,
  password,
  select,
  spinner,
  text,
} from "@clack/prompts";
import { startMcpServer } from "@inthezon/mcp-server";
import {
  BackendClient,
  clearLocalSession,
  getConfigPath,
  HttpError,
  loadLocalState,
  normalizeBackendUrl,
  saveLocalState,
  type CreateAmazonAccountInput,
} from "@inthezon/shared-sdk";
import pc from "picocolors";

type MarketplaceOption = {
  label: string;
  country: string;
  marketplaceId: string;
};

const MARKETPLACES: MarketplaceOption[] = [
  { label: "Italy", country: "IT", marketplaceId: "APJ6JRA9NG5V4" },
  { label: "Germany", country: "DE", marketplaceId: "A1PA6795UKMFR9" },
  { label: "France", country: "FR", marketplaceId: "A13V1IB3VIYZZH" },
  { label: "Spain", country: "ES", marketplaceId: "A1RKKUPIHCS9HS" },
  { label: "United Kingdom", country: "GB", marketplaceId: "A1F83G8C2ARO7P" },
  { label: "United States", country: "US", marketplaceId: "ATVPDKIKX0DER" },
  { label: "Canada", country: "CA", marketplaceId: "A2EUQ1WTGCTBG2" },
];

function renderHero(): string {
  return [
    pc.cyan("  ___       _   _                    "),
    pc.cyan(" |_ _|_ __ | |_| |__   ___ _______  _"),
    pc.cyan("  | || '_ \\| __| '_ \\ / _ \\_  / _ \\| |"),
    pc.cyan("  | || | | | |_| | | |  __// / (_) | |"),
    pc.cyan(" |___|_| |_|\\__|_| |_|\\___/___\\___/|_|"),
    "",
    pc.dim("Amazon MCP local para Codex e Claude Code"),
  ].join("\n");
}

function printHelp(): void {
  console.log(`
${pc.bold("Inthezon CLI")}

Usage:
  inthezon
  inthezon register
  inthezon login
  inthezon status
  inthezon logout
  inthezon setup-amazon
  inthezon connect-account
  inthezon accounts
  inthezon doctor
  inthezon mcp start
  inthezon mcp config
  `);
}

async function promptText(message: string, initialValue?: string, placeholder?: string): Promise<string> {
  const answer = await text({
    message,
    initialValue,
    placeholder,
    validate(value) {
      if (!value || !String(value).trim()) {
        return "Required";
      }
    },
  });
  if (isCancel(answer)) {
    process.exit(1);
  }
  return String(answer).trim();
}

async function promptOptionalText(message: string, initialValue?: string, placeholder?: string): Promise<string | undefined> {
  const answer = await text({
    message,
    initialValue,
    placeholder,
  });
  if (isCancel(answer)) {
    process.exit(1);
  }
  const value = String(answer).trim();
  return value ? value : undefined;
}

async function promptOptionalSecret(message: string): Promise<string | undefined> {
  const answer = await password({
    message,
  });
  if (isCancel(answer)) {
    process.exit(1);
  }
  const value = String(answer);
  return value ? value : undefined;
}

async function promptPassword(message: string): Promise<string> {
  const answer = await password({
    message,
    validate(value) {
      if (!value || value.length < 8) {
        return "Use at least 8 characters";
      }
    },
  });
  if (isCancel(answer)) {
    process.exit(1);
  }
  return String(answer);
}

async function resolveClient(requireSession = true): Promise<{ state: ReturnType<typeof loadLocalState>; client: BackendClient }> {
  const state = loadLocalState();
  if (requireSession && (!state.accessToken || !state.refreshToken)) {
    throw new Error("No active session found. Run `inthezon login` first.");
  }

  const client = new BackendClient({
    backendUrl: state.backendUrl,
    accessToken: state.accessToken,
    refreshToken: state.refreshToken,
    onSessionUpdate(tokens) {
      saveLocalState({
        ...loadLocalState(),
        accessToken: tokens.access_token,
        refreshToken: tokens.refresh_token,
      });
    },
  });

  return { state, client };
}

async function commandRegister(): Promise<void> {
  intro(pc.bold("Create your Inthezon account"));

  const existing = loadLocalState();
  const backendUrl = normalizeBackendUrl(
    await promptText("Backend URL", existing.backendUrl, "http://localhost:8000"),
  );
  const fullName = await promptText("Full name");
  const email = await promptText("Email");
  const userPassword = await promptPassword("Password");

  const spin = spinner();
  spin.start("Creating account");

  try {
    const client = new BackendClient({ backendUrl });
    await client.register({
      email,
      password: userPassword,
      full_name: fullName,
    });
    const tokens = await client.login({ email, password: userPassword });
    const user = await client.getMe();
    const organization = await client.getOrganization();

    saveLocalState({
      backendUrl,
      accessToken: tokens.access_token,
      refreshToken: tokens.refresh_token,
      user,
      organization,
      lastLoginAt: new Date().toISOString(),
    });

    spin.stop("Account created");
    note(
      `User: ${user.email}\nOrganization: ${organization.name}\nConfig: ${getConfigPath()}`,
      "Session saved",
    );
    outro("Run `inthezon setup-amazon` next.");
  } catch (error) {
    spin.stop("Registration failed");
    handleError(error);
  }
}

async function commandLogin(): Promise<void> {
  intro(pc.bold("Login to Inthezon"));

  const existing = loadLocalState();
  const backendUrl = normalizeBackendUrl(
    await promptText("Backend URL", existing.backendUrl, "http://localhost:8000"),
  );
  const email = await promptText("Email", existing.user?.email);
  const userPassword = await promptPassword("Password");

  const spin = spinner();
  spin.start("Authenticating");

  try {
    const client = new BackendClient({ backendUrl });
    const tokens = await client.login({ email, password: userPassword });
    const user = await client.getMe();
    const organization = await client.getOrganization();

    saveLocalState({
      backendUrl,
      accessToken: tokens.access_token,
      refreshToken: tokens.refresh_token,
      user,
      organization,
      lastLoginAt: new Date().toISOString(),
    });

    spin.stop("Authenticated");
    note(
      `User: ${user.email}\nOrganization: ${organization.name}\nBackend: ${backendUrl}`,
      "Session ready",
    );
    outro("Run `inthezon mcp config` to wire Codex or Claude Code.");
  } catch (error) {
    spin.stop("Login failed");
    handleError(error);
  }
}

async function commandStatus(): Promise<void> {
  intro(pc.bold("Inthezon status"));

  try {
    const { state, client } = await resolveClient(true);
    const spin = spinner();
    spin.start("Checking backend and session");

    const [health, user, organization, apiKeys, accounts] = await Promise.all([
      client.health(),
      client.getMe(),
      client.getOrganization(),
      client.getOrganizationApiKeys(),
      client.listAccounts(),
    ]);

    saveLocalState({
      ...state,
      user,
      organization,
    });

    spin.stop("Status loaded");
    note(
      [
        `Backend: ${state.backendUrl}`,
        `Health: ${health.status} (${health.environment})`,
        `User: ${user.email}`,
        `Organization: ${organization.name}`,
        `Accounts: ${accounts.length}`,
        `SP-API client ID: ${apiKeys.sp_api_client_id || "not set"}`,
        `AWS key: ${apiKeys.sp_api_aws_access_key || "not set"}`,
      ].join("\n"),
      "Current session",
    );
    outro("Done.");
  } catch (error) {
    handleError(error);
  }
}

async function commandLogout(): Promise<void> {
  intro(pc.bold("Logout"));
  clearLocalSession();
  outro("Local session cleared.");
}

async function commandSetupAmazon(): Promise<void> {
  intro(pc.bold("Amazon SP-API setup"));

  try {
    const { client } = await resolveClient(true);
    const current = await client.getOrganizationApiKeys();

    note(
      [
        `Client ID: ${current.sp_api_client_id || "not set"}`,
        `Client secret: ${current.has_client_secret ? "saved" : "not set"}`,
        `AWS access key: ${current.sp_api_aws_access_key || "not set"}`,
        `AWS secret key: ${current.has_aws_secret_key ? "saved" : "not set"}`,
        `Role ARN: ${current.sp_api_role_arn || "not set"}`,
      ].join("\n"),
      "Current backend values",
    );

    const clientId = await promptOptionalText("SP-API client ID", undefined, "Leave blank to keep current value");
    const clientSecret = await promptOptionalSecret("SP-API client secret");
    const awsAccessKey = await promptOptionalText("AWS access key", undefined, "Leave blank to keep current value");
    const awsSecretKey = await promptOptionalSecret("AWS secret key");
    const roleArn = await promptOptionalText("AWS role ARN", current.sp_api_role_arn || undefined, "Leave blank to keep current value");

    const payload = Object.fromEntries(
      Object.entries({
        sp_api_client_id: clientId,
        sp_api_client_secret: clientSecret,
        sp_api_aws_access_key: awsAccessKey,
        sp_api_aws_secret_key: awsSecretKey,
        sp_api_role_arn: roleArn,
      }).filter(([, value]) => value !== undefined),
    );

    if (Object.keys(payload).length === 0) {
      outro("Nothing changed.");
      return;
    }

    const spin = spinner();
    spin.start("Saving credentials");
    const result = await client.updateOrganizationApiKeys(payload);
    spin.stop("Credentials saved");

    note(
      [
        `Client ID: ${result.sp_api_client_id || "not set"}`,
        `Client secret: ${result.has_client_secret ? "saved" : "not set"}`,
        `AWS access key: ${result.sp_api_aws_access_key || "not set"}`,
        `AWS secret key: ${result.has_aws_secret_key ? "saved" : "not set"}`,
        `Role ARN: ${result.sp_api_role_arn || "not set"}`,
      ].join("\n"),
      "Stored on backend",
    );
    outro("Amazon credentials updated.");
  } catch (error) {
    handleError(error);
  }
}

async function commandConnectAccount(): Promise<void> {
  intro(pc.bold("Connect an Amazon account"));

  try {
    const { client } = await resolveClient(true);

    const accountName = await promptText("Account name");
    const accountType = await select({
      message: "Account type",
      options: [
        { value: "seller", label: "Seller" },
        { value: "vendor", label: "Vendor" },
      ],
    });
    if (isCancel(accountType)) {
      process.exit(1);
    }

    const marketplace = await select({
      message: "Marketplace",
      options: MARKETPLACES.map((option) => ({
        value: option.marketplaceId,
        label: `${option.label} (${option.country})`,
        hint: option.marketplaceId,
      })),
    });
    if (isCancel(marketplace)) {
      process.exit(1);
    }

    const selectedMarketplace = MARKETPLACES.find((option) => option.marketplaceId === marketplace);
    if (!selectedMarketplace) {
      throw new Error("Invalid marketplace selection.");
    }

    const refreshToken = await promptOptionalSecret("SP-API refresh token");
    const loginEmail = await promptOptionalText("Amazon login email", undefined, "Optional");
    const loginPassword = loginEmail
      ? await promptOptionalSecret("Amazon login password")
      : undefined;

    const payload: CreateAmazonAccountInput = {
      account_name: accountName,
      account_type: String(accountType) as CreateAmazonAccountInput["account_type"],
      marketplace_country: selectedMarketplace.country,
      marketplace_id: selectedMarketplace.marketplaceId,
      refresh_token: refreshToken,
      login_email: loginEmail,
      login_password: loginPassword,
    };

    const spin = spinner();
    spin.start("Creating account");
    const account = await client.createAccount(payload);
    spin.stop("Account created");

    const shouldTest = refreshToken
      ? await confirm({ message: "Test the connection now?", initialValue: true })
      : false;
    if (isCancel(shouldTest)) {
      process.exit(1);
    }
    if (shouldTest) {
      spin.start("Testing connection");
      await client.testAccountConnection(account.id);
      spin.stop("Connection test passed");
    }

    const shouldSync = await confirm({ message: "Trigger an initial sync now?", initialValue: true });
    if (isCancel(shouldSync)) {
      process.exit(1);
    }
    if (shouldSync) {
      spin.start("Queueing initial sync");
      await client.triggerAccountSync(account.id);
      spin.stop("Initial sync queued");
    }

    note(
      [
        `ID: ${account.id}`,
        `Name: ${account.account_name}`,
        `Marketplace: ${account.marketplace_country} (${account.marketplace_id})`,
        `Refresh token: ${account.has_refresh_token ? "saved" : "not saved"}`,
      ].join("\n"),
      "Account connected",
    );
    outro("Account setup complete.");
  } catch (error) {
    handleError(error);
  }
}

async function commandAccounts(): Promise<void> {
  intro(pc.bold("Connected accounts"));

  try {
    const { client } = await resolveClient(true);
    const accounts = await client.listAccounts();

    if (accounts.length === 0) {
      outro("No accounts connected yet.");
      return;
    }

    note(
      accounts
        .map((account) =>
          [
            `${account.account_name} (${account.account_type})`,
            `  id: ${account.id}`,
            `  marketplace: ${account.marketplace_country}`,
            `  sync: ${account.sync_status}`,
            `  refresh token: ${account.has_refresh_token ? "yes" : "no"}`,
          ].join("\n"),
        )
        .join("\n\n"),
      `${accounts.length} account(s)`,
    );
    outro("Done.");
  } catch (error) {
    handleError(error);
  }
}

async function commandDoctor(): Promise<void> {
  intro(pc.bold("Diagnostics"));

  try {
    const state = loadLocalState();
    const client = new BackendClient({
      backendUrl: state.backendUrl,
      accessToken: state.accessToken,
      refreshToken: state.refreshToken,
    });

    const health = await client.health();
    const summary: string[] = [
      `Backend URL: ${state.backendUrl}`,
      `Backend health: ${health.status}`,
      `Config path: ${getConfigPath()}`,
      `Logged in: ${state.accessToken ? "yes" : "no"}`,
    ];

    if (state.accessToken) {
      try {
        const me = await client.getMe();
        summary.push(`Current user: ${me.email}`);
      } catch (error) {
        summary.push(`Current user: failed (${formatError(error)})`);
      }
    }

    note(summary.join("\n"), "Doctor");
    outro("Done.");
  } catch (error) {
    handleError(error);
  }
}

async function commandMcpConfig(): Promise<void> {
  intro(pc.bold("MCP config"));
  const snippet = {
    mcpServers: {
      inthezon: {
        command: "inthezon",
        args: ["mcp", "start"],
      },
    },
  };

  note(
    `${JSON.stringify(snippet, null, 2)}\n\nLogin first with \`inthezon login\` so the MCP can reuse your saved session.`,
    "Config snippet",
  );
  outro("Copy this into the MCP config used by Codex or Claude Code.");
}

async function launchMenu(): Promise<void> {
  intro(renderHero());

  while (true) {
    const state = loadLocalState();
    const summary = [
      `Backend: ${state.backendUrl}`,
      `Session: ${state.user?.email || "not logged in"}`,
      `Org: ${state.organization?.name || "not loaded"}`,
    ].join("\n");

    note(summary, "Current context");

    const choice = await select({
      message: "What do you want to do?",
      options: [
        { value: "login", label: "Login", hint: "Authenticate with an existing account" },
        { value: "register", label: "Register", hint: "Create account and sign in" },
        { value: "setup-amazon", label: "Setup Amazon", hint: "Save SP-API and AWS credentials" },
        { value: "connect-account", label: "Connect Account", hint: "Attach a seller/vendor account" },
        { value: "accounts", label: "Accounts", hint: "List connected Amazon accounts" },
        { value: "status", label: "Status", hint: "Check session and backend health" },
        { value: "mcp-config", label: "MCP Config", hint: "Show config for Codex and Claude Code" },
        { value: "doctor", label: "Doctor", hint: "Run local diagnostics" },
        { value: "logout", label: "Logout", hint: "Clear local session" },
        { value: "exit", label: "Exit", hint: "Close the TUI" },
      ],
    });

    if (isCancel(choice) || choice === "exit") {
      outro("See you.");
      return;
    }

    if (choice === "login") {
      await commandLogin();
    } else if (choice === "register") {
      await commandRegister();
    } else if (choice === "setup-amazon") {
      await commandSetupAmazon();
    } else if (choice === "connect-account") {
      await commandConnectAccount();
    } else if (choice === "accounts") {
      await commandAccounts();
    } else if (choice === "status") {
      await commandStatus();
    } else if (choice === "mcp-config") {
      await commandMcpConfig();
    } else if (choice === "doctor") {
      await commandDoctor();
    } else if (choice === "logout") {
      await commandLogout();
    }
  }
}

function formatError(error: unknown): string {
  if (error instanceof HttpError) {
    return `${error.message} (HTTP ${error.status})`;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}

function handleError(error: unknown): never {
  outro(pc.red(formatError(error)));
  process.exit(1);
}

async function main(): Promise<void> {
  const [command, subcommand] = process.argv.slice(2);

  if (!command) {
    await launchMenu();
    return;
  }

  if (command === "--help" || command === "-h" || command === "help") {
    printHelp();
    return;
  }

  if (command === "register") {
    await commandRegister();
    return;
  }

  if (command === "login") {
    await commandLogin();
    return;
  }

  if (command === "status") {
    await commandStatus();
    return;
  }

  if (command === "logout") {
    await commandLogout();
    return;
  }

  if (command === "setup-amazon") {
    await commandSetupAmazon();
    return;
  }

  if (command === "connect-account") {
    await commandConnectAccount();
    return;
  }

  if (command === "accounts") {
    await commandAccounts();
    return;
  }

  if (command === "doctor") {
    await commandDoctor();
    return;
  }

  if (command === "mcp" && subcommand === "start") {
    await startMcpServer();
    return;
  }

  if (command === "mcp" && subcommand === "config") {
    await commandMcpConfig();
    return;
  }

  printHelp();
  process.exitCode = 1;
}

main().catch((error) => {
  handleError(error);
});
