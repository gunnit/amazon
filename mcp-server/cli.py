"""Inthezon MCP Manager — interactive CLI for profiles, accounts, defaults, diagnostics."""
from __future__ import annotations

import asyncio
import sys
from urllib.parse import urlparse

import questionary
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from config import (
    load_config,
    save_config,
    get_active_profile,
    get_defaults,
    set_active_profile,
    upsert_profile,
    delete_profile,
    update_selected_accounts,
    update_defaults,
)

console = Console()


# ─── DB helper ──────────────────────────────────────────────────────────────


async def _query_db(database_url: str, sql: str, params: dict | None = None) -> list[dict]:
    """Run a query against the given database URL and return rows as dicts."""
    engine = create_async_engine(database_url, pool_size=1)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text(sql), params or {})
            return [dict(r._mapping) for r in result]
    finally:
        await engine.dispose()


def _run(coro):
    """Run an async coroutine from sync context."""
    return asyncio.run(coro)


def _short_url(database_url: str) -> str:
    """Extract host/dbname from a database URL for display."""
    try:
        parsed = urlparse(database_url.replace("postgresql+asyncpg", "postgresql"))
        host = parsed.hostname or "localhost"
        db = (parsed.path or "/").lstrip("/") or "?"
        return f"{host}/{db}"
    except Exception:
        return database_url[:40]


# ─── Header ─────────────────────────────────────────────────────────────────


def _show_header():
    name, profile = get_active_profile()
    defaults = get_defaults()
    url_short = _short_url(profile.get("database_url", ""))
    acct_ids = profile.get("selected_account_ids", [])
    acct_label = f"{len(acct_ids)} selected" if acct_ids else "All"
    console.print()
    console.print(Panel(
        f"[bold]Profile:[/bold] {name} ({url_short})\n"
        f"[bold]Accounts:[/bold] {acct_label}  [dim]│[/dim]  "
        f"[bold]Range:[/bold] {defaults.get('date_range_days', 30)}d  [dim]│[/dim]  "
        f"[bold]Group:[/bold] {defaults.get('group_by', 'day')}  [dim]│[/dim]  "
        f"[bold]Limit:[/bold] {defaults.get('limit', 100)}",
        title="[bold cyan]Inthezon MCP Manager[/bold cyan]",
        border_style="cyan",
    ))


# ─── Main menu ──────────────────────────────────────────────────────────────


def main():
    while True:
        _show_header()
        choice = questionary.select(
            "What would you like to do?",
            choices=[
                "Profiles      — manage database connections",
                "Accounts      — select active Amazon accounts",
                "Defaults      — configure query defaults",
                "Diagnostics   — connectivity & system health",
                "Exit",
            ],
        ).ask()
        if choice is None or "Exit" in choice:
            console.print("[dim]Goodbye.[/dim]")
            break
        if "Profiles" in choice:
            _profiles_menu()
        elif "Accounts" in choice:
            _accounts_menu()
        elif "Defaults" in choice:
            _defaults_menu()
        elif "Diagnostics" in choice:
            _diagnostics_menu()


# ─── Profiles ───────────────────────────────────────────────────────────────


def _profiles_menu():
    while True:
        choice = questionary.select(
            "Profiles",
            choices=[
                "Switch profile",
                "Add profile",
                "Edit profile",
                "Delete profile",
                "Back",
            ],
        ).ask()
        if choice is None or choice == "Back":
            return
        if choice == "Switch profile":
            _profile_switch()
        elif choice == "Add profile":
            _profile_add()
        elif choice == "Edit profile":
            _profile_edit()
        elif choice == "Delete profile":
            _profile_delete()


def _profile_switch():
    config = load_config()
    active = config.get("active_profile", "")
    profiles = config.get("profiles", {})
    if not profiles:
        console.print("[yellow]No profiles configured.[/yellow]")
        return
    choices = [f"{'✓ ' if k == active else '  '}{k} ({_short_url(v.get('database_url', ''))})"
               for k, v in profiles.items()]
    ans = questionary.select("Select profile:", choices=choices).ask()
    if ans is None:
        return
    name = ans.strip().lstrip("✓").strip().split(" (")[0]
    set_active_profile(name)
    console.print(f"[green]Switched to profile '{name}'[/green]")


def _profile_add():
    name = questionary.text("Profile name:").ask()
    if not name:
        return
    url = questionary.text("DATABASE_URL (postgresql+asyncpg://...):").ask()
    if not url:
        return
    upsert_profile(name.strip(), url.strip())
    console.print(f"[green]Profile '{name.strip()}' created.[/green]")


def _profile_edit():
    config = load_config()
    profiles = config.get("profiles", {})
    if not profiles:
        console.print("[yellow]No profiles to edit.[/yellow]")
        return
    names = list(profiles.keys())
    name = questionary.select("Edit which profile?", choices=names).ask()
    if not name:
        return
    current_url = profiles[name].get("database_url", "")
    new_url = questionary.text("New DATABASE_URL:", default=current_url).ask()
    if new_url and new_url != current_url:
        upsert_profile(name, new_url.strip())
        console.print(f"[green]Profile '{name}' updated.[/green]")


def _profile_delete():
    config = load_config()
    active = config.get("active_profile", "")
    profiles = config.get("profiles", {})
    deletable = [k for k in profiles if k != active]
    if not deletable:
        console.print("[yellow]No profiles available to delete (cannot delete the active one).[/yellow]")
        return
    name = questionary.select("Delete which profile?", choices=deletable).ask()
    if not name:
        return
    if questionary.confirm(f"Delete profile '{name}'?", default=False).ask():
        delete_profile(name)
        console.print(f"[green]Profile '{name}' deleted.[/green]")


# ─── Accounts ───────────────────────────────────────────────────────────────


def _accounts_menu():
    name, profile = get_active_profile()
    db_url = profile.get("database_url", "")
    if not db_url:
        console.print("[red]No database URL configured for this profile.[/red]")
        return

    console.print("[dim]Fetching accounts from database...[/dim]")
    try:
        accounts = _run(_query_db(db_url, (
            "SELECT id, account_name, account_type, marketplace_country, "
            "is_active, sync_status FROM amazon_accounts ORDER BY account_name"
        )))
    except Exception as e:
        console.print(f"[red]DB error: {e}[/red]")
        return

    if not accounts:
        console.print("[yellow]No accounts found in the database.[/yellow]")
        return

    # Show table
    table = Table(title="Amazon Accounts", show_lines=False)
    table.add_column("Name", style="bold")
    table.add_column("Type")
    table.add_column("Marketplace")
    table.add_column("Active")
    table.add_column("Sync")
    for a in accounts:
        table.add_row(
            str(a.get("account_name", "")),
            str(a.get("account_type", "")),
            str(a.get("marketplace_country", "")),
            "✓" if a.get("is_active") else "✗",
            str(a.get("sync_status", "")),
        )
    console.print(table)

    # Checkbox multi-select
    current_ids = set(profile.get("selected_account_ids", []))
    choices = [
        questionary.Choice(
            title=f"{a['account_name']} ({a['account_type']}, {a.get('marketplace_country', '?')})",
            value=str(a["id"]),
            checked=str(a["id"]) in current_ids,
        )
        for a in accounts
    ]
    selected = questionary.checkbox(
        "Select accounts to filter (empty = all):",
        choices=choices,
    ).ask()
    if selected is None:
        return
    update_selected_accounts(selected)
    label = f"{len(selected)} accounts" if selected else "All accounts (no filter)"
    console.print(f"[green]Saved: {label}[/green]")


# ─── Defaults ───────────────────────────────────────────────────────────────


def _defaults_menu():
    while True:
        defaults = get_defaults()
        choice = questionary.select(
            "Defaults",
            choices=[
                f"Date range:    {defaults.get('date_range_days', 30)} days",
                f"Default limit: {defaults.get('limit', 100)}",
                f"Group by:      {defaults.get('group_by', 'day')}",
                "Back",
            ],
        ).ask()
        if choice is None or choice == "Back":
            return
        if "Date range" in choice:
            ans = questionary.select(
                "Date range (days):",
                choices=["7", "30", "90", "Custom"],
            ).ask()
            if ans == "Custom":
                ans = questionary.text("Enter number of days:").ask()
            if ans and ans.isdigit():
                update_defaults({"date_range_days": int(ans)})
                console.print(f"[green]Date range set to {ans} days.[/green]")
        elif "Default limit" in choice:
            ans = questionary.text(
                "Default limit:",
                default=str(defaults.get("limit", 100)),
            ).ask()
            if ans and ans.isdigit():
                update_defaults({"limit": int(ans)})
                console.print(f"[green]Limit set to {ans}.[/green]")
        elif "Group by" in choice:
            ans = questionary.select(
                "Group by:",
                choices=["day", "week", "month"],
            ).ask()
            if ans:
                update_defaults({"group_by": ans})
                console.print(f"[green]Group by set to '{ans}'.[/green]")


# ─── Diagnostics ────────────────────────────────────────────────────────────


def _diagnostics_menu():
    _, profile = get_active_profile()
    db_url = profile.get("database_url", "")
    selected_ids = profile.get("selected_account_ids", [])

    console.print()
    console.print("[bold]Running diagnostics...[/bold]")

    checks: list[str] = []

    # DB connectivity
    try:
        _run(_query_db(db_url, "SELECT 1"))
        checks.append("[green]✓[/green] DB connectivity")
    except Exception as e:
        checks.append(f"[red]✗[/red] DB connectivity — {e}")
        # Can't continue without DB
        for line in checks:
            console.print(f"  {line}")
        questionary.press_any_key_to_continue("Press Enter to return...").ask()
        return

    # Accounts
    try:
        rows = _run(_query_db(db_url,
            "SELECT account_type, COUNT(*) AS cnt FROM amazon_accounts GROUP BY account_type"
        ))
        parts = ", ".join(f"{r['cnt']} {r['account_type']}" for r in rows)
        total = sum(r["cnt"] for r in rows)
        checks.append(f"[green]✓[/green] Accounts: {total} total ({parts})")
    except Exception as e:
        checks.append(f"[red]✗[/red] Accounts — {e}")

    # Sales data
    try:
        rows = _run(_query_db(db_url,
            "SELECT COUNT(*) AS cnt, MIN(date)::text AS min_d, MAX(date)::text AS max_d FROM sales_data"
        ))
        r = rows[0]
        if r["cnt"] > 0:
            checks.append(
                f"[green]✓[/green] Sales data: {r['cnt']:,} rows ({r['min_d']} → {r['max_d']})"
            )
        else:
            checks.append("[yellow]![/yellow] Sales data: 0 rows")
    except Exception as e:
        checks.append(f"[red]✗[/red] Sales data — {e}")

    # Products
    try:
        rows = _run(_query_db(db_url,
            "SELECT COUNT(*) AS cnt FROM products WHERE is_active = true"
        ))
        checks.append(f"[green]✓[/green] Products: {rows[0]['cnt']:,} active")
    except Exception as e:
        checks.append(f"[red]✗[/red] Products — {e}")

    # Inventory
    try:
        rows = _run(_query_db(db_url, "SELECT COUNT(*) AS cnt FROM inventory_data"))
        checks.append(f"[green]✓[/green] Inventory snapshots: {rows[0]['cnt']:,} rows")
    except Exception as e:
        checks.append(f"[red]✗[/red] Inventory — {e}")

    # Selected accounts
    if selected_ids:
        try:
            rows = _run(_query_db(db_url, "SELECT COUNT(*) AS cnt FROM amazon_accounts"))
            total = rows[0]["cnt"]
            checks.append(f"[cyan]→[/cyan] Selected accounts: {len(selected_ids)} of {total}")
        except Exception:
            checks.append(f"[cyan]→[/cyan] Selected accounts: {len(selected_ids)}")
    else:
        checks.append("[cyan]→[/cyan] Selected accounts: All (no filter)")

    console.print()
    for line in checks:
        console.print(f"  {line}")
    console.print()
    questionary.press_any_key_to_continue("Press Enter to return...").ask()


# ─── Entry ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted.[/dim]")
        sys.exit(0)
