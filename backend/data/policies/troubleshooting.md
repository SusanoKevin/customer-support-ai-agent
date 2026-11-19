# Troubleshooting Guides

## Login problems
Tiers: free, pro, enterprise
If a user cannot sign in, confirm the email address, then send a password reset link. Reset links expire after 30 minutes. Enterprise users on SSO must sign in through their identity provider; password resets do not apply to them.

## Sync is delayed
Tiers: free, pro, enterprise
Project sync normally completes within 2 minutes. Ask the user to refresh and check the status page. If sync is delayed more than 30 minutes, create a ticket with the project name and approximate time of the last successful sync.

## API rate limit errors
Tiers: pro, enterprise
Pro accounts are limited to 600 API requests per minute and Enterprise to 3000. A 429 response means the limit was hit; clients should retry with exponential backoff. Persistent 429s below the limit should be escalated.

## Billing page not loading
Tiers: pro, enterprise
Clear browser cache or try a private window. Only workspace owners and billing admins can view the billing page. If the user has the correct role and the page still fails, create a ticket.
