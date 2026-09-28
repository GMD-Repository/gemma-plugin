# -*- coding: utf-8 -*-
"""
Unit tests for send_release_email.py (scripts/release/send_release_email.py).
Tests email parsing, batch chunking, template rendering, message construction,
and SMTP batch delivery.
"""

from __future__ import annotations

import tempfile
import unittest
from email.message import EmailMessage
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.release.send_release_email import (
    DEFAULT_BATCH_SIZE,
    build_email_html,
    build_email_text,
    chunk_recipients,
    create_email_message,
    parse_email_list,
    resolve_recipients,
    send_batch_emails,
)


class TestSendReleaseEmail(unittest.TestCase):
    """Test suite for release email blast batching and delivery."""

    def test_parse_email_list_formats_and_deduplication(self):
        """Test parsing emails separated by commas, spaces, newlines, and semicolons."""
        raw = """
        alice@example.com, bob@example.com; charlie@example.com
        Dave <dave@example.com>
        ALICE@EXAMPLE.COM
        invalid-email-address
        test.user+tag@domain.co.uk
        """
        parsed = parse_email_list(raw)
        expected = [
            "alice@example.com",
            "bob@example.com",
            "charlie@example.com",
            "dave@example.com",
            "test.user+tag@domain.co.uk",
        ]
        self.assertEqual(parsed, expected)

    def test_parse_email_list_empty(self):
        """Test parsing empty or whitespace-only inputs."""
        self.assertEqual(parse_email_list(""), [])
        self.assertEqual(parse_email_list("   \n\t  "), [])
        self.assertEqual(parse_email_list([]), [])

    def test_chunk_recipients(self):
        """Test chunking recipients into batches of defined size."""
        recipients = [f"user_{i}@example.com" for i in range(1, 101)]

        # Chunk with size 40 -> 3 batches: 40, 40, 20
        batches = chunk_recipients(recipients, batch_size=40)
        self.assertEqual(len(batches), 3)
        self.assertEqual(len(batches[0]), 40)
        self.assertEqual(len(batches[1]), 40)
        self.assertEqual(len(batches[2]), 20)

        # Chunk with size 100 -> 1 batch: 100
        batches_100 = chunk_recipients(recipients, batch_size=100)
        self.assertEqual(len(batches_100), 1)
        self.assertEqual(len(batches_100[0]), 100)

        # Ensure no data loss
        reconstructed = [email for batch in batches for email in batch]
        self.assertEqual(reconstructed, recipients)

    def test_chunk_recipients_invalid_batch_size(self):
        """Test that non-positive batch size raises ValueError."""
        with self.assertRaises(ValueError):
            chunk_recipients(["a@b.com"], batch_size=0)

        with self.assertRaises(ValueError):
            chunk_recipients(["a@b.com"], batch_size=-5)

    def test_build_email_html_content(self):
        """Test HTML email generation with required metadata and links."""
        html = build_email_html(
            version="3.2.0",
            zip_name="gemma-plugin-v3.2.0.zip",
            release_body="<li>Fixed point snapping</li>",
            repo="GMD-Repository/gemma-plugin",
            doc_url="https://gemma-plugin.vercel.app/getting-started.html",
        )
        self.assertIn("v3.2.0", html)
        self.assertIn("gemma-plugin-v3.2.0.zip", html)
        self.assertIn("Fixed point snapping", html)
        self.assertIn("https://gemma-plugin.vercel.app/getting-started.html", html)
        self.assertIn("https://github.com/GMD-Repository/gemma-plugin/releases/download/v3.2.0/gemma-plugin-v3.2.0.zip", html)

    def test_build_email_text_content(self):
        """Test plain text fallback generation."""
        text = build_email_text(
            version="3.2.0",
            zip_name="gemma-plugin-v3.2.0.zip",
            release_body="<li>Fixed point snapping</li>",
            repo="GMD-Repository/gemma-plugin",
        )
        self.assertIn("v3.2.0", text)
        self.assertIn("gemma-plugin-v3.2.0.zip", text)
        self.assertIn("- Fixed point snapping", text)

    def test_create_email_message_bcc_privacy(self):
        """Test that EmailMessage sets Subject, From, To, but does NOT leak BCC in headers."""
        msg = create_email_message(
            subject="Release Ready",
            from_addr="sender@example.com",
            to_addr="sender@example.com",
            reply_to="reply@example.com",
            html_content="<p>Hello</p>",
            text_content="Hello",
        )
        self.assertEqual(msg["Subject"], "Release Ready")
        self.assertEqual(msg["From"], "sender@example.com")
        self.assertEqual(msg["To"], "sender@example.com")
        self.assertEqual(msg["Reply-To"], "reply@example.com")
        # Ensure Bcc header is absent so recipient clients never see the blast list
        self.assertIsNone(msg["Bcc"])
        self.assertTrue(msg.is_multipart())

    def test_send_batch_emails_dry_run(self):
        """Test that dry-run mode does not open SMTP connections."""
        recipients = [f"recip_{i}@example.com" for i in range(50)]
        with patch("smtplib.SMTP_SSL") as mock_smtp:
            result = send_batch_emails(
                server_address="smtp.gmail.com",
                server_port=465,
                username="test_user",
                password="test_password",
                from_addr="sender@example.com",
                to_addr="sender@example.com",
                reply_to="reply@example.com",
                subject="Test",
                html_content="<p>Test</p>",
                text_content="Test",
                recipients=recipients,
                batch_size=20,
                delay_seconds=0,
                dry_run=True,
            )
            self.assertTrue(result)
            mock_smtp.assert_not_called()

    def test_send_batch_emails_delivery_and_envelope_split(self):
        """Test that send_batch_emails delivers in batches via SMTP."""
        recipients = [f"recip_{i}@example.com" for i in range(1, 15)]  # 14 recipients
        mock_server = MagicMock()

        with patch("smtplib.SMTP_SSL", return_value=mock_server):
            result = send_batch_emails(
                server_address="smtp.gmail.com",
                server_port=465,
                username="test_user",
                password="test_password",
                from_addr="sender@example.com",
                to_addr="sender@example.com",
                reply_to="reply@example.com",
                subject="Test",
                html_content="<p>Test</p>",
                text_content="Test",
                recipients=recipients,
                batch_size=5,  # 14 / 5 -> 3 batches (5, 5, 4)
                delay_seconds=0,
                dry_run=False,
            )

            self.assertTrue(result)
            mock_server.login.assert_called_once_with("test_user", "test_password")
            # Should have called send_message 3 times (5, 5, 4)
            self.assertEqual(mock_server.send_message.call_count, 3)

            # Check envelope recipients for each call
            first_call_args = mock_server.send_message.call_args_list[0]
            self.assertEqual(first_call_args.kwargs["from_addr"], "sender@example.com")
            # Envelope should be [to_addr] + 5 recipients = 6
            self.assertEqual(len(first_call_args.kwargs["to_addrs"]), 6)
            self.assertEqual(first_call_args.kwargs["to_addrs"][0], "sender@example.com")
            self.assertEqual(first_call_args.kwargs["to_addrs"][1:], recipients[0:5])

            third_call_args = mock_server.send_message.call_args_list[2]
            self.assertEqual(len(third_call_args.kwargs["to_addrs"]), 5)  # 1 to_addr + 4 recipients
            self.assertEqual(third_call_args.kwargs["to_addrs"][1:], recipients[10:14])

            mock_server.quit.assert_called_once()

    def test_resolve_recipients_precedence(self):
        """Test recipient resolution precedence (CLI > File > Env > Fallback)."""
        args_mock = MagicMock()
        args_mock.recipients = "cli@example.com"
        args_mock.recipients_file = ""

        # 1. CLI wins
        with patch.dict("os.environ", {"RECIPIENTS": "env@example.com"}):
            resolved = resolve_recipients(args_mock)
            self.assertEqual(resolved, ["cli@example.com"])

        # 2. File when CLI empty
        args_mock.recipients = ""
        with tempfile.NamedTemporaryFile("w+", delete=False, encoding="utf-8") as tf:
            tf.write("file1@example.com, file2@example.com\n")
            temp_path = tf.name

        try:
            args_mock.recipients_file = temp_path
            with patch.dict("os.environ", {"RECIPIENTS": "env@example.com"}):
                resolved = resolve_recipients(args_mock)
                self.assertEqual(resolved, ["file1@example.com", "file2@example.com"])
        finally:
            Path(temp_path).unlink(missing_ok=True)

        # 3. Environment variable RECIPIENTS
        args_mock.recipients_file = ""
        with patch.dict("os.environ", {"RECIPIENTS": "env1@example.com, env2@example.com"}):
            resolved = resolve_recipients(args_mock)
            self.assertEqual(resolved, ["env1@example.com", "env2@example.com"])

        # 4. Fallback EMAIL_TO
        with patch.dict("os.environ", {"RECIPIENTS": "", "EMAIL_TO": "fallback@example.com"}):
            resolved = resolve_recipients(args_mock)
            self.assertEqual(resolved, ["fallback@example.com"])

    def test_main_uses_html_body_env(self):
        """Test that main() uses HTML_BODY environment variable when provided."""
        from scripts.release.send_release_email import main

        custom_html = "<html><body><h1>Custom Release Notice</h1></body></html>"
        with patch.dict(
            "os.environ",
            {
                "HTML_BODY": custom_html,
                "RECIPIENTS": "user@example.com",
                "MAIL_USERNAME": "test_user",
                "MAIL_PASSWORD": "test_password",
            },
        ):
            with patch("scripts.release.send_release_email.send_batch_emails") as mock_send:
                mock_send.return_value = True
                with patch("sys.argv", ["send_release_email.py", "--dry-run"]):
                    main()
                    mock_send.assert_called_once()
                    call_kwargs = mock_send.call_args[1]
                    self.assertIn("<h1>Custom Release Notice</h1>", call_kwargs["html_content"])
                    self.assertIn("font-family", call_kwargs["html_content"])

    def test_render_template_placeholders(self):
        """Test that both GitHub Actions and Python style placeholders are resolved."""
        from scripts.release.send_release_email import render_template

        raw_template = "Version: ${{ steps.release.outputs.version }} | Body: {formatted_body} | Repo: {repo}"
        rendered = render_template(
            template=raw_template,
            version="3.5.0",
            zip_name="gemma-3.5.0.zip",
            release_body="Resolved bug",
            repo="GMD-Repository/gemma-plugin",
        )
        self.assertEqual(rendered, "Version: 3.5.0 | Body: Resolved bug | Repo: GMD-Repository/gemma-plugin")
        self.assertNotIn("{formatted_body}", rendered)
        self.assertNotIn("${{ steps.release.outputs.version }}", rendered)

    def test_inline_email_styles(self):
        """Test that CSS classes are converted to inline styles for email client compatibility."""
        from scripts.release.send_release_email import inline_email_styles

        raw = '<div class="box"><div class="box-title">Title</div></div><a href="https://gemma-plugin.vercel.app/getting-started.html" class="button">Docs</a>'
        styled = inline_email_styles(raw)
        self.assertIn('style="background-color: #f8fafc', styled)
        self.assertIn('style="font-size: 15px', styled)
        self.assertIn('background-color: #2563a8', styled)


if __name__ == "__main__":
    unittest.main()
