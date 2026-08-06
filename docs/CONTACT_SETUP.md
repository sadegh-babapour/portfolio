# Contact Service Setup

The public form is safe to display without configuration, but submission stays
disabled until every required database, Turnstile, and email-API setting is present.
Never paste real secret values into Git, an issue, or a project document.

## Local environment

The ignored local environment file is:

```text
/home/god/Documents/bizqlab/portfolio/.env
```

Copy the contact variable names from `.env.example` into that file. Generate
the two application secrets separately so they are not equal:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Use the first value for `CONTACT_TOKEN_PEPPER` and the second for
`CONTACT_IP_HASH_KEY`.

For local Turnstile testing, use Cloudflare's published always-pass test pair:

```dotenv
TURNSTILE_SITE_KEY=1x00000000000000000000AA
TURNSTILE_SECRET_KEY=1x0000000000000000000000000000000AA
TURNSTILE_EXPECTED_HOSTNAMES=localhost,127.0.0.1
```

Never put those test credentials in Railway production.

## Cloudflare Turnstile production widget

1. Create or sign in to a Cloudflare account.
2. Open the Cloudflare dashboard and select **Turnstile**.
3. Select **Add widget**.
4. Name it `BizQLab Contact`, choose **Managed**, and add `bizqlab.com` as the
   authorized hostname. Cloudflare treats its subdomains, including
   `www.bizqlab.com`, as authorized.
5. Create the widget, then copy its **sitekey** and **secret key**. The sitekey
   is public; the secret key belongs only in local `.env` and Railway variables.

Production values:

```dotenv
TURNSTILE_SITE_KEY=<widget sitekey>
TURNSTILE_SECRET_KEY=<widget secret key>
TURNSTILE_EXPECTED_HOSTNAMES=bizqlab.com,www.bizqlab.com
```

The server verifies every token through Siteverify and also checks the
`hostname` and `action=contact` response fields. Tokens expire after five
minutes and are single-use.

## Transactional email through Resend

Railway Hobby blocks outbound SMTP, so the contact workflow sends through
Resend's HTTPS API while Zoho remains the owner mailbox and reply client.

1. Create a Resend account and add a sending domain. A dedicated subdomain such
   as `contact.bizqlab.com` isolates automated-mail reputation.
2. Copy Resend's exact SPF and DKIM records into Cloudflare DNS and wait until
   Resend reports the domain as verified.
3. Create a sending-only API key and store it only in the ignored local `.env`
   and the Railway `portfolio` service.
4. Choose a sender on the exact verified domain and the Zoho inbox that should
   receive verified messages.

Set:

```dotenv
CONTACT_FROM_EMAIL=<sender on the verified Resend domain>
CONTACT_TO_EMAIL=<your destination inbox>
RESEND_API_KEY=<sending-only Resend API key>
```

The application never impersonates the visitor as the sender. Resend sends as
`CONTACT_FROM_EMAIL`; the application sets the verified visitor address as
`Reply-To`, so the owner can reply normally from Zoho.

## Railway portfolio service

Add the following variables to the `portfolio` service in the production
environment:

```dotenv
DATABASE_URL=${{Postgres.DATABASE_URL}}
CONTACT_PUBLIC_BASE_URL=https://bizqlab.com
CONTACT_ALLOWED_ORIGINS=https://bizqlab.com,https://www.bizqlab.com
CONTACT_TOKEN_PEPPER=<generated secret 1>
CONTACT_IP_HASH_KEY=<generated secret 2>
TURNSTILE_SITE_KEY=<production sitekey>
TURNSTILE_SECRET_KEY=<production secret>
TURNSTILE_EXPECTED_HOSTNAMES=bizqlab.com,www.bizqlab.com
CONTACT_FROM_EMAIL=<sender on verified Resend domain>
CONTACT_TO_EMAIL=<destination inbox>
RESEND_API_KEY=<sending-only Resend API key>
```

Configure this pre-deploy command on the `portfolio` service:

```bash
alembic upgrade head
```

This creates and migrates only the dedicated `portfolio` schema. It does not
modify the independently owned `transit` schema.

## Verification checklist

1. Open `/contact` on desktop and mobile and complete the Turnstile check.
2. Submit a test message and confirm the response does not disclose account
   state.
3. Open the verification email once; confirm the final message arrives with the
   visitor as `Reply-To`.
4. Open the same verification link again; it must report unavailable.
5. Submit invalid, expired, and repeated requests and confirm safe errors and
   throttling.
6. Confirm no passwords, tokens, raw IP addresses, or email bodies appear in
   application logs.
