#!/usr/bin/env python3
"""
GEMMA Plugin — Batch Release Email Blast Script

Sends release announcement emails in batches via SMTP to circumvent provider
recipient limits (specifically Gmail's strict limit of 100 recipients per message).

Features:
- Recipient list parsing, normalization, validation, and deduplication.
- Dynamic batching (default: 80 recipients/batch) with safety margin (<100).
- BCC privacy protection: envelope recipients receive emails without exposing
  the recipient list in the message headers.
- Plain text + HTML MIME multipart message creation with official GEMMA styling.
- Configurable delay between batches to respect SMTP rate limits.
- Masking of email addresses in GitHub Actions logs to protect PII.
- Fallback recipient sourcing (CLI -> Env -> File -> GSheet -> EMAIL_TO).
- Dry-run mode for simulation and testing.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import smtplib
import ssl
import sys
import time
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr
from pathlib import Path
from typing import Any

# Ensure repo root is on Python path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("send_release_email")

DEFAULT_BATCH_SIZE = 80
DEFAULT_DELAY_SECONDS = 2.0
DEFAULT_SMTP_SERVER = "smtp.gmail.com"
DEFAULT_SMTP_PORT = 465
DEFAULT_DOC_URL = "https://gemma-plugin.vercel.app/getting-started.html"
DEFAULT_CHANGELOG_URL = "https://gemma-plugin.vercel.app/changelog.html"
DEFAULT_REPO = "GMD-Repository/gemma-plugin"

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


def parse_email_list(raw_input: str | list[str]) -> list[str]:
    """Parse, clean, validate, and deduplicate email addresses.

    Accepts comma, semicolon, space, or newline-separated strings, or lists of strings.
    Preserves order of first appearance.
    """
    if isinstance(raw_input, list):
        items = raw_input
    else:
        if not raw_input or not raw_input.strip():
            return []
        items = re.split(r"[,;\r\n\s]+", raw_input)

    valid_emails: list[str] = []
    seen: set[str] = set()

    for item in items:
        # Extract pure email from potential 'Name <email@domain>' format
        _, addr = parseaddr(item.strip())
        addr = addr.strip().lower()
        if not addr:
            continue
        if EMAIL_REGEX.match(addr):
            if addr not in seen:
                seen.add(addr)
                valid_emails.append(addr)
        else:
            logger.debug("Skipping invalid email token: %s", item)

    return valid_emails


def chunk_recipients(recipients: list[str], batch_size: int = DEFAULT_BATCH_SIZE) -> list[list[str]]:
    """Split recipients into batches of size at most batch_size."""
    if batch_size <= 0:
        raise ValueError(f"batch_size must be a positive integer, got {batch_size}")
    if not recipients:
        return []
    return [recipients[i : i + batch_size] for i in range(0, len(recipients), batch_size)]


def build_email_html(
    version: str,
    zip_name: str,
    release_body: str,
    repo: str = DEFAULT_REPO,
    doc_url: str = DEFAULT_DOC_URL,
    changelog_url: str = DEFAULT_CHANGELOG_URL,
) -> str:
    """Build the HTML announcement email body using GEMMA template styling with robust inline styles."""
    formatted_body = release_body.strip()
    if "<" not in formatted_body and ">" not in formatted_body:
        formatted_body = formatted_body.replace("\n", "<br>")

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>GEMMA Plugin Notification</title>
  <style>
    body {{
      font-family: Arial, Helvetica, sans-serif;
      line-height: 1.5;
      color: #333333;
      margin: 0;
      padding: 0;
      background-color: #f5f5f5;
    }}
    .email-container {{
      max-width: 600px;
      margin: 16px auto;
      background-color: #ffffff;
      border: 1px solid #e2e8f0;
      border-radius: 6px;
      overflow: hidden;
      font-family: Arial, Helvetica, sans-serif;
    }}
    .content {{
      padding: 24px;
    }}
    .title {{
      font-size: 20px;
      font-weight: bold;
      color: #1e293b;
      margin-bottom: 8px;
    }}
    .text {{
      font-size: 14px;
      color: #555555;
      line-height: 1.5;
      margin-bottom: 12px;
    }}
    .box {{
      background-color: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 6px;
      padding: 16px;
      margin: 14px 0;
    }}
    .box-title {{
      font-size: 15px;
      font-weight: bold;
      color: #0f172a;
      margin-bottom: 6px;
    }}
    .button-group {{
      margin-top: 12px;
      margin-bottom: 12px;
    }}
    .button {{
      display: inline-block;
      padding: 8px 12px;
      text-decoration: none;
      border-radius: 4px;
      font-size: 12px;
      font-weight: bold;
      margin-right: 6px;
      margin-top: 4px;
      margin-bottom: 4px;
      text-align: center;
      white-space: nowrap;
      box-sizing: border-box;
    }}
    @media only screen and (max-width: 600px) {{
      .email-container {{
        width: 100% !important;
        margin: 0 !important;
        border-radius: 0 !important;
        border-left: none !important;
        border-right: none !important;
      }}
      .content {{
        padding: 16px !important;
      }}
      .box {{
        padding: 14px !important;
        margin: 12px 0 !important;
      }}
      .button-group {{
        display: block !important;
        width: 100% !important;
        margin-top: 10px !important;
        margin-bottom: 10px !important;
      }}
      .button {{
        display: block !important;
        width: 100% !important;
        margin-right: 0 !important;
        margin-left: 0 !important;
        margin-top: 6px !important;
        margin-bottom: 6px !important;
        padding: 11px 16px !important;
        font-size: 13px !important;
        text-align: center !important;
        box-sizing: border-box !important;
      }}
    }}
  </style>
</head>
<body style="font-family: Arial, Helvetica, sans-serif; line-height: 1.5; color: #333333; margin: 0; padding: 0; background-color: #f5f5f5;">
  <div class="email-container" style="max-width: 600px; margin: 16px auto; background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; overflow: hidden; font-family: Arial, Helvetica, sans-serif;">
    <div class="content" style="padding: 24px;">
      <div class="title" style="font-size: 20px; font-weight: bold; color: #1e293b; margin-bottom: 8px;">Release Announcement: GEMMA Plugin v{version}</div>
      <div class="text" style="font-size: 14px; color: #555555; line-height: 1.5; margin-bottom: 12px;">
        We are pleased to formally announce the production release of the <strong>GEMMA Plugin</strong> (Version
        <strong>{version}</strong>).
      </div>

      <!-- Release Summary -->
      <div class="box" style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 16px; margin: 14px 0;">
        <div class="box-title" style="font-size: 15px; font-weight: bold; color: #0f172a; margin-bottom: 6px;">Release Summary</div>
        <div class="text" style="font-size: 14px; color: #555555; line-height: 1.5; margin: 4px 0;"><strong>Product:</strong> GEMMA QGIS Plugin</div>
        <div class="text" style="font-size: 14px; color: #555555; line-height: 1.5; margin: 4px 0;"><strong>Version:</strong> {version}</div>
        <div class="text" style="font-size: 14px; color: #555555; line-height: 1.5; margin: 4px 0;"><strong>Platform:</strong> QGIS Plugin (.zip)</div>
        <div class="text" style="font-size: 14px; color: #555555; line-height: 1.5; margin: 4px 0;"><strong>Status:</strong> Official Production / General Availability</div>
      </div>

      <!-- Changelog & Highlights -->
      <div class="box" style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 16px; margin: 14px 0;">
        <div class="box-title" style="font-size: 15px; font-weight: bold; color: #0f172a; margin-bottom: 6px;">Changelog &amp; Highlights</div>
        <div class="text" style="font-size: 14px; color: #555555; line-height: 1.5; margin: 4px 0;">
          {formatted_body}
        </div>
      </div>

      <!-- Installation & Deployment -->
      <div class="box" style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 16px; margin: 14px 0;">
        <div class="box-title" style="font-size: 15px; font-weight: bold; color: #0f172a; margin-bottom: 6px;">Installation &amp; Deployment</div>

        <div class="text" style="font-size: 14px; color: #555555; line-height: 1.5; margin-bottom: 10px;">
          <strong>QGIS Repository Installation:</strong> If your QGIS client is connected to the official GEMMA
          repository, QGIS will automatically prompt you for update. Open QGIS and navigate to <em>Plugins &rarr;
          Manage and Install Plugins &rarr; GEMMA &rarr; Upgrade / Install Plugin</em>.
        </div>

        <div class="text" style="font-size: 14px; color: #555555; line-height: 1.5; margin-bottom: 12px;">
          <strong>Manual Download &amp; Documentation:</strong> You may also download the official release package
          directly or review technical documentation:
        </div>

        <div class="button-group" style="margin-top: 12px; margin-bottom: 12px;">
          <a href="{doc_url}"
             class="button"
             style="display: inline-block; background-color: #2563a8; color: #ffffff !important; padding: 8px 12px; text-decoration: none; border-radius: 4px; font-size: 12px; font-weight: bold; margin-right: 6px; margin-top: 4px; margin-bottom: 4px; text-align: center; white-space: nowrap; box-sizing: border-box;"
             target="_blank">
            View Documentation
          </a>

          <a href="{changelog_url}"
             class="button"
             style="display: inline-block; background-color: #0d9488; color: #ffffff !important; padding: 8px 12px; text-decoration: none; border-radius: 4px; font-size: 12px; font-weight: bold; margin-right: 6px; margin-top: 4px; margin-bottom: 4px; text-align: center; white-space: nowrap; box-sizing: border-box;"
             target="_blank">
            View Changelog
          </a>

          <a href="https://github.com/{repo}/releases/download/v{version}/{zip_name}"
             class="button"
             style="display: inline-block; background-color: #475569; color: #ffffff !important; padding: 8px 12px; text-decoration: none; border-radius: 4px; font-size: 12px; font-weight: bold; margin-top: 4px; margin-bottom: 4px; text-align: center; white-space: nowrap; box-sizing: border-box;"
             target="_blank">
            Download Release Package
          </a>
        </div>

        <div style="margin-top: 8px; font-size: 12px; color: #777777; line-height: 1.4;">
          If the direct package link is unavailable, assets may still be propagating.
          You can access the
          <a href="https://github.com/{repo}/releases"
             style="color: #2563a8; text-decoration: none;"
             target="_blank">
            Official Releases Directory
          </a>.
        </div>
      </div>
    </div>
  </div>
</body>
</html>
"""


def render_template(
    template: str,
    version: str,
    zip_name: str,
    release_body: str,
    repo: str = DEFAULT_REPO,
    doc_url: str = DEFAULT_DOC_URL,
    changelog_url: str = DEFAULT_CHANGELOG_URL,
) -> str:
    """Safely replace all variable placeholders in both GitHub Actions and Python formats."""
    rendered = template
    replacements = {
        "${{ steps.release.outputs.version }}": version,
        "${{ steps.release.outputs.zip_name }}": zip_name,
        "${{ steps.release.outputs.release_body_html || steps.release.outputs.release_body }}": release_body,
        "${{ steps.release.outputs.release_body }}": release_body,
        "${{ steps.release.outputs.release_body_html }}": release_body,
        "${{ steps.release.outputs.changelog_url }}": changelog_url,
        "${{ github.repository }}": repo,
        "{version}": version,
        "{zip_name}": zip_name,
        "{formatted_body}": release_body,
        "{release_body}": release_body,
        "{repo}": repo,
        "{doc_url}": doc_url,
        "{changelog_url}": changelog_url,
    }
    for placeholder, val in replacements.items():
        rendered = rendered.replace(placeholder, val)
    return rendered


def inline_email_styles(html_str: str, changelog_url: str = DEFAULT_CHANGELOG_URL) -> str:
    """Ensure email clients (like Gmail/Outlook) that strip <style> blocks render properly.

    Inlines essential styles directly onto elements that only have CSS class attributes.
    """
    if not html_str:
        return ""

    result = html_str

    # Ensure body has font-family
    result = re.sub(
        r"<body([^>]*)>",
        lambda m: f'<body{m.group(1)} style="font-family: Arial, Helvetica, sans-serif; line-height: 1.5; color: #333333; margin: 0; padding: 0; background-color: #f5f5f5;">'
        if "font-family" not in m.group(1)
        else m.group(0),
        result,
    )

    # Class mappings with corresponding inline style definitions
    class_styles = [
        ('class="email-container"', 'class="email-container" style="max-width: 600px; margin: 16px auto; background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; overflow: hidden; font-family: Arial, Helvetica, sans-serif;"'),
        ('class="content"', 'class="content" style="padding: 24px; font-family: Arial, Helvetica, sans-serif;"'),
        ('class="title"', 'class="title" style="font-size: 20px; font-weight: bold; color: #1e293b; margin-bottom: 8px; font-family: Arial, Helvetica, sans-serif;"'),
        ('class="box"', 'class="box" style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 16px; margin: 14px 0; font-family: Arial, Helvetica, sans-serif;"'),
        ('class="box-title"', 'class="box-title" style="font-size: 15px; font-weight: bold; color: #0f172a; margin-bottom: 6px; font-family: Arial, Helvetica, sans-serif;"'),
        ('class="list"', 'class="list" style="font-size: 14px; margin: 6px 0; font-family: Arial, Helvetica, sans-serif;"'),
        ('class="button-group"', 'class="button-group" style="margin-top: 12px; margin-bottom: 12px;"'),
    ]

    for cls_attr, styled_attr in class_styles:
        # Match class="..." only if not followed by style=
        pattern = re.compile(re.escape(cls_attr) + r"(?![^>]*style=)")
        result = pattern.sub(styled_attr, result)

    # Ensure "View Documentation" button has inline background color (not transparent)
    result = re.sub(
        r'<a([^>]+)href="[^"]*getting-started[^"]*"([^>]*)>',
        lambda m: m.group(0).replace(
            m.group(0),
            f'<a{m.group(1)}href="https://gemma-plugin.vercel.app/getting-started.html"{m.group(2)} style="display: inline-block; background-color: #2563a8; color: #ffffff !important; padding: 8px 12px; text-decoration: none; border-radius: 4px; font-size: 12px; font-weight: bold; margin-right: 6px; margin-top: 4px; margin-bottom: 4px; text-align: center; white-space: nowrap; box-sizing: border-box;">'
        ) if "background-color" not in m.group(0) else m.group(0),
        result,
    )

    # Ensure "View Changelog" button has inline background color
    result = re.sub(
        r'<a([^>]+)href="[^"]*changelog[^"]*"([^>]*)>',
        lambda m: m.group(0).replace(
            m.group(0),
            f'<a{m.group(1)}href="{changelog_url}"{m.group(2)} style="display: inline-block; background-color: #0d9488; color: #ffffff !important; padding: 8px 12px; text-decoration: none; border-radius: 4px; font-size: 12px; font-weight: bold; margin-right: 6px; margin-top: 4px; margin-bottom: 4px; text-align: center; white-space: nowrap; box-sizing: border-box;">'
        ) if "background-color" not in m.group(0) else m.group(0),
        result,
    )

    # Ensure "Download Release Package" button has complete button styles
    result = re.sub(
        r'<a([^>]+)href="[^"]*releases/download[^"]*"([^>]*)style="([^"]*)"([^>]*)>',
        lambda m: f'<a{m.group(1)}href="{re.search(r"href=[\'\"]([^\'\"]+)[\'\"]", m.group(0)).group(1)}"{m.group(2)}style="display: inline-block; background-color: #475569; color: #ffffff !important; padding: 8px 12px; text-decoration: none; border-radius: 4px; font-size: 12px; font-weight: bold; margin-top: 4px; margin-bottom: 4px; text-align: center; white-space: nowrap; box-sizing: border-box;"{m.group(4)}>',
        result,
    )

    return result


def build_email_text(
    version: str,
    zip_name: str,
    release_body: str,
    repo: str = DEFAULT_REPO,
    doc_url: str = DEFAULT_DOC_URL,
    changelog_url: str = DEFAULT_CHANGELOG_URL,
) -> str:
    """Build the plain text fallback announcement email body."""
    # Convert simple HTML highlights to plain text lines
    clean_body = re.sub(r"<li[^>]*>(.*?)</li>", r"- \1\n", release_body, flags=re.DOTALL)
    clean_body = re.sub(r"<[^>]+>", "", clean_body)
    clean_lines = [line.strip() for line in clean_body.splitlines() if line.strip()]
    plain_highlights = "\n".join(clean_lines) if clean_lines else release_body.strip()

    return f"""============================================================
Release Announcement: GEMMA Plugin v{version}
============================================================

We are pleased to formally announce the production release of the GEMMA Plugin (Version {version}).

Release Summary:
- Product: GEMMA QGIS Plugin
- Version: {version}
- Platform: QGIS Plugin (.zip)
- Status: Official Production / General Availability

Changelog & Highlights:
{plain_highlights}

Installation & Deployment:
- QGIS Repository Installation: Open QGIS and navigate to Plugins -> Manage and Install Plugins -> GEMMA -> Upgrade / Install Plugin.
- Documentation: {doc_url}
- Changelog: {changelog_url}
- Download Release Package: https://github.com/{repo}/releases/download/v{version}/{zip_name}
- Official Releases: https://github.com/{repo}/releases
"""


def create_email_message(
    subject: str,
    from_addr: str,
    to_addr: str,
    reply_to: str,
    html_content: str,
    text_content: str,
) -> EmailMessage:
    """Create a multipart EmailMessage.

    NOTE: The recipient list is NOT included in the message headers (BCC privacy).
    Recipients receive the message via envelope recipients (to_addrs in SMTP).
    """
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    if reply_to:
        msg["Reply-To"] = reply_to
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain="psa.gov.ph")

    msg.set_content(text_content)
    msg.add_alternative(html_content, subtype="html")
    return msg


def send_batch_emails(
    server_address: str,
    server_port: int,
    username: str,
    password: str,
    from_addr: str,
    to_addr: str,
    reply_to: str,
    subject: str,
    html_content: str,
    text_content: str,
    recipients: list[str],
    batch_size: int = DEFAULT_BATCH_SIZE,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    dry_run: bool = False,
) -> bool:
    """Send emails to all recipients in batches via SMTP.

    Returns True if all batches were sent successfully.
    """
    if not recipients:
        logger.warning("No recipient email addresses provided.")
        return True

    batches = chunk_recipients(recipients, batch_size=batch_size)
    total_recipients = len(recipients)
    total_batches = len(batches)

    logger.info(
        "Preparing to send email blast to %d recipients across %d batch(es) (batch size: %d)",
        total_recipients,
        total_batches,
        batch_size,
    )

    if dry_run:
        logger.info("[DRY RUN] Simulating email sending:")
        for idx, batch in enumerate(batches, start=1):
            logger.info(
                "[DRY RUN] Batch %d/%d: Would send to %d recipients (Envelope total: %d)",
                idx,
                total_batches,
                len(batch),
                len(batch) + 1,
            )
        return True

    # Extract clean envelope sender address
    _, clean_from = parseaddr(from_addr)
    _, clean_to = parseaddr(to_addr)
    clean_sender = clean_from or username

    context = ssl.create_default_context()
    smtp_conn = None

    try:
        def connect_smtp():
            if server_port == 465:
                s = smtplib.SMTP_SSL(server_address, server_port, context=context, timeout=30)
            else:
                s = smtplib.SMTP(server_address, server_port, timeout=30)
                s.starttls(context=context)
            s.login(username, password)
            return s

        smtp_conn = connect_smtp()
        logger.info("Successfully connected and authenticated to %s:%d", server_address, server_port)

        for idx, batch in enumerate(batches, start=1):
            msg = create_email_message(
                subject=subject,
                from_addr=from_addr,
                to_addr=to_addr,
                reply_to=reply_to,
                html_content=html_content,
                text_content=text_content,
            )

            envelope_recipients = [clean_to] + batch
            logger.info(
                "Sending Batch %d/%d (%d recipients, envelope count: %d)...",
                idx,
                total_batches,
                len(batch),
                len(envelope_recipients),
            )

            try:
                smtp_conn.send_message(
                    msg,
                    from_addr=clean_sender,
                    to_addrs=envelope_recipients,
                )
            except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError) as conn_err:
                logger.warning("SMTP connection lost on batch %d (%s). Reconnecting...", idx, conn_err)
                smtp_conn = connect_smtp()
                smtp_conn.send_message(
                    msg,
                    from_addr=clean_sender,
                    to_addrs=envelope_recipients,
                )

            logger.info("✅ Batch %d/%d delivered successfully.", idx, total_batches)

            if idx < total_batches and delay_seconds > 0:
                time.sleep(delay_seconds)

        logger.info("🎉 All %d email recipient(s) notified successfully across %d batch(es).", total_recipients, total_batches)
        return True

    except Exception as err:
        logger.error("❌ Failed to send email blast: %s", err, exc_info=True)
        return False
    finally:
        if smtp_conn:
            try:
                smtp_conn.quit()
            except Exception:
                pass


def resolve_recipients(args: argparse.Namespace) -> list[str]:
    """Resolve recipients from CLI args, environment variables, files, or Google Sheet fallback."""
    # 1. Direct CLI argument
    if args.recipients:
        parsed = parse_email_list(args.recipients)
        if parsed:
            logger.info("Loaded %d recipient(s) from CLI --recipients", len(parsed))
            return parsed

    # 2. File specified via CLI
    if args.recipients_file:
        p = Path(args.recipients_file)
        if p.exists():
            content = p.read_text(encoding="utf-8")
            parsed = parse_email_list(content)
            if parsed:
                logger.info("Loaded %d recipient(s) from file: %s", len(parsed), p)
                return parsed

    # 3. Environment variable RECIPIENTS (e.g. from GitHub Actions output)
    env_recipients = os.environ.get("RECIPIENTS", "").strip()
    if env_recipients:
        parsed = parse_email_list(env_recipients)
        if parsed:
            logger.info("Loaded %d recipient(s) from RECIPIENTS environment variable", len(parsed))
            return parsed

    # 4. Default recipient files in repository
    for default_path in [REPO_ROOT / ".recipients.txt", REPO_ROOT / "scripts" / "release" / ".recipients.txt"]:
        if default_path.exists():
            content = default_path.read_text(encoding="utf-8").strip()
            parsed = parse_email_list(content)
            if parsed:
                logger.info("Loaded %d recipient(s) from %s", len(parsed), default_path)
                return parsed

    # 5. Direct Google Sheet fetch if credentials exist
    spreadsheet_id = os.environ.get("GSHEET_SPREADSHEET_ID") or os.environ.get("GSPREAD_SPREADSHEET_ID", "")
    if spreadsheet_id and (os.environ.get("GCP_SA_KEY") or os.environ.get("GSHEET_CREDENTIALS")):
        try:
            from scripts.release.gsheet_release import fetch_emails, get_gspread_client

            client = get_gspread_client()
            if client:
                emails = fetch_emails(client, spreadsheet_id, worksheet_name=args.worksheet_emails)
                if emails:
                    logger.info("Fetched %d recipient(s) directly from Google Sheet", len(emails))
                    return emails
        except Exception as err:
            logger.warning("Could not fetch recipients directly from Google Sheet: %s", err)

    # 6. Fallback email from secret/env
    fallback = os.environ.get("EMAIL_TO_FALLBACK") or os.environ.get("EMAIL_TO", "")
    if fallback.strip():
        parsed = parse_email_list(fallback)
        if parsed:
            logger.info("Using %d fallback recipient(s) from EMAIL_TO", len(parsed))
            return parsed

    return []


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="GEMMA Plugin Batch Release Email Blast")
    parser.add_argument("--version", default="", help="Plugin release version (e.g. 3.1.0)")
    parser.add_argument("--zip-name", default="", help="Plugin zip file name (e.g. gemma-plugin-3.1.0.zip)")
    parser.add_argument("--release-body", default="", help="Changelog or release summary (markdown or HTML)")
    parser.add_argument("--repo", default="", help="GitHub repository (e.g. GMD-Repository/gemma-plugin)")
    parser.add_argument("--doc-url", default=DEFAULT_DOC_URL, help="Documentation site URL")
    parser.add_argument("--changelog-url", default=DEFAULT_CHANGELOG_URL, help="Changelog site URL")

    # Recipient options
    parser.add_argument("--recipients", default="", help="Comma-separated recipient emails")
    parser.add_argument("--recipients-file", default="", help="Path to text file containing recipient emails")
    parser.add_argument("--worksheet-emails", default="email_gemma", help="Google Sheet worksheet name")

    # SMTP connection options
    parser.add_argument("--server-address", default="", help="SMTP server host (default: smtp.gmail.com)")
    parser.add_argument("--server-port", type=int, default=0, help="SMTP server port (default: 465)")
    parser.add_argument("--username", default="", help="SMTP username")
    parser.add_argument("--password", default="", help="SMTP password / app token")
    parser.add_argument("--from-addr", default="", help="Sender email address")
    parser.add_argument("--to-addr", default="", help="Visible 'To' email address")
    parser.add_argument("--reply-to", default="", help="Reply-To email address")
    parser.add_argument("--subject", default="", help="Custom email subject")
    parser.add_argument("--html-body", default="", help="Full HTML body content")
    parser.add_argument("--html-file", default="", help="Path to file containing HTML body")
    parser.add_argument("--text-body", default="", help="Full plain text body content")

    # Batching controls
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Max recipients per message")
    parser.add_argument("--delay-seconds", type=float, default=DEFAULT_DELAY_SECONDS, help="Delay between batches")
    parser.add_argument("--dry-run", action="store_true", help="Simulate execution without sending emails")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    version = args.version or os.environ.get("RELEASE_VERSION", "")
    if not version:
        # Try reading version from metadata.txt
        metadata_file = REPO_ROOT / "metadata.txt"
        if metadata_file.exists():
            for line in metadata_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("version="):
                    version = line.split("=", 1)[1].strip()
                    break
    if not version:
        version = "unknown"

    zip_name = args.zip_name or os.environ.get("ZIP_NAME", f"gemma-plugin-v{version}.zip")
    release_body = args.release_body or os.environ.get("RELEASE_BODY", "")
    if not release_body:
        release_body = "<p>Maintenance and performance improvements.</p>"

    repo = args.repo or os.environ.get("GITHUB_REPOSITORY", DEFAULT_REPO)
    doc_url = args.doc_url or os.environ.get("DOC_URL", DEFAULT_DOC_URL)
    changelog_url = args.changelog_url or os.environ.get("CHANGELOG_URL", DEFAULT_CHANGELOG_URL)

    # SMTP configuration
    server_address = args.server_address or os.environ.get("SMTP_SERVER") or os.environ.get("MAIL_SERVER") or DEFAULT_SMTP_SERVER
    server_port = args.server_port or int(os.environ.get("SMTP_PORT") or os.environ.get("MAIL_PORT") or DEFAULT_SMTP_PORT)
    username = args.username or os.environ.get("MAIL_USERNAME", "")
    password = args.password or os.environ.get("MAIL_PASSWORD", "")
    from_addr = args.from_addr or os.environ.get("MAIL_FROM") or username
    reply_to = args.reply_to or os.environ.get("MAIL_REPLY_TO") or from_addr
    to_addr = args.to_addr or from_addr
    subject = args.subject or os.environ.get("SUBJECT") or os.environ.get("MAIL_SUBJECT") or f"[GEMMA Plugin] v{version} — Stable Release Ready"

    recipients = resolve_recipients(args)
    if not recipients:
        logger.warning("No email recipients found. Skipping release email notification.")
        return

    # Mask recipient emails in GitHub Actions logs
    if os.environ.get("GITHUB_ACTIONS"):
        for email in recipients:
            print(f"::add-mask::{email}")

    logger.info("Found %d unique recipient(s) for v%s email blast.", len(recipients), version)

    # If SMTP credentials are not present and not dry-run, log warning and exit cleanly
    if not args.dry_run and (not username or not password):
        logger.warning("SMTP credentials (MAIL_USERNAME/MAIL_PASSWORD) not configured. Skipping email delivery.")
        return

    html_content = args.html_body or os.environ.get("HTML_BODY", "")
    if not html_content and args.html_file and Path(args.html_file).exists():
        html_content = Path(args.html_file).read_text(encoding="utf-8")
    if not html_content:
        html_content = build_email_html(
            version=version,
            zip_name=zip_name,
            release_body=release_body,
            repo=repo,
            doc_url=doc_url,
            changelog_url=changelog_url,
        )
    else:
        # Resolve placeholders (both GitHub Actions ${{ ... }} and Python {placeholder})
        html_content = render_template(
            template=html_content,
            version=version,
            zip_name=zip_name,
            release_body=release_body,
            repo=repo,
            doc_url=doc_url,
            changelog_url=changelog_url,
        )

    # Automatically inline styles to prevent email clients from stripping <style> tags
    html_content = inline_email_styles(html_content, changelog_url=changelog_url)

    text_content = args.text_body or os.environ.get("TEXT_BODY", "")
    if not text_content:
        text_content = build_email_text(
            version=version,
            zip_name=zip_name,
            release_body=html_content or release_body,
            repo=repo,
            doc_url=doc_url,
            changelog_url=changelog_url,
        )

    success = send_batch_emails(
        server_address=server_address,
        server_port=server_port,
        username=username,
        password=password,
        from_addr=from_addr,
        to_addr=to_addr,
        reply_to=reply_to,
        subject=subject,
        html_content=html_content,
        text_content=text_content,
        recipients=recipients,
        batch_size=args.batch_size,
        delay_seconds=args.delay_seconds,
        dry_run=args.dry_run,
    )

    if not success and not args.dry_run:
        sys.exit(1)


if __name__ == "__main__":
    main()
