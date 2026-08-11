#!/usr/bin/env python3
"""
Standalone development script to smoke test Resend email provider delivery.
Usage:
    python scripts/send_resend_smoke_test.py recipient@example.com

Options:
    --provider: resend (default), console, smtp
"""

import asyncio
import argparse
import sys
from pathlib import Path

# Ensure root directory is in sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from app.config import settings, validate_runtime_configuration
from app.services.recommendation_email_service import email_provider


async def main():
    parser = argparse.ArgumentParser(description="SmartReco Email Smoke Test")
    parser.add_argument("recipient", help="Recipient email address")
    parser.add_argument(
        "--provider",
        default=settings.email_provider or "resend",
        help="Email provider (console, smtp, resend)",
    )
    args = parser.parse_args()

    # Override provider if specified
    settings.email_provider = args.provider

    try:
        validate_runtime_configuration(settings)
    except Exception as exc:
        print(f"Configuration Error: {exc}", file=sys.stderr)
        sys.exit(1)

    provider_instance = email_provider()

    subject = "SmartReco Resend Email Transport Smoke Test"
    text = "Hello!\n\nThis is a real-world smoke test email from SmartReco using the Resend email provider.\n\nHappy Learning!"
    html = """
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;">
        <h2 style="color: #4f46e5;">SmartReco Email Transport Verification</h2>
        <p>This is a real-world smoke test email confirming that the <strong>Resend</strong> email transport is active and working correctly in SmartReco.</p>
        <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;" />
        <p style="font-size: 12px; color: #666;">SmartReco Automated Recommendation Engine</p>
    </div>
    """

    print(f"Provider: {settings.email_provider}")
    print(f"Recipient: {args.recipient}")

    result = await provider_instance.send_recommendation_digest(
        recipient=args.recipient,
        subject=subject,
        text=text,
        html=html,
    )

    print(f"Success: {result.success}")
    print(f"Provider Message ID: {result.message_id}")
    if result.error:
        print(f"Error: {result.error}")
        print(f"Permanent Failure: {result.permanent}")

    if not result.success:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
