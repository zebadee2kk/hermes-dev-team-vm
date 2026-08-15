# Telegram owner-governance adapter

Forge uses Telegram only as a compact owner interface. The Forge governance API remains the source of truth. Telegram receives no general Forge credential, capability grant, project workspace or unrestricted command surface.

## Long polling first

The first deployment uses Telegram Bot API `getUpdates` long polling rather than a webhook. Telegram documents `getUpdates` and webhooks as mutually exclusive. Long polling avoids adding public HTTPS ingress to the Forge host.

On startup the service calls `deleteWebhook` with `drop_pending_updates=false`, then requests only `callback_query` updates and advances the offset after handled updates.

Official Bot API: https://core.telegram.org/bots/api

A webhook adapter may be added later. If so, Telegram's `secret_token` / `X-Telegram-Bot-Api-Secret-Token` mechanism is mandatory in addition to the same owner and callback validation.

## Mobile-safe summaries are a separate trusted statement

A decision record is **not automatically safe to send to Telegram**.

The Telegram adapter exposes a local Unix-socket notification API. A trusted control-plane caller submits only:

- exact `decision_id`;
- `mobile_safe: true/false`;
- a maximum 600-character `mobile_safe_summary` only when `mobile_safe=true`.

The adapter re-fetches the actual decision from the control-plane governance API and accepts only an open decision. The full decision question, recommendation, evidence and project context are never used to render an actionable Telegram gate.

This separation is intentional: a worker that can propose or influence a decision cannot self-label the decision content as safe for an external messaging service. The notification UDS additionally requires a separate transport credential and must not be exposed to Hands.

For `mobile_safe=false`, Telegram receives only a generic notice that a restricted Forge gate exists. No action buttons are attached.

## Owner controls

Mobile-safe gates expose only:

- `YES`
- `NO`
- `DEFER` when the persisted decision classification allows it
- `MORE INFO`

Telegram documents `InlineKeyboardButton.callback_data` as 1–64 bytes and warns that clients may send arbitrary callback data. Forge therefore uses a short authenticated callback rather than trusting raw button data.

The callback contains:

```text
version : action-code : truncated-SHA256 decision key : HMAC
```

The HMAC is bound to the configured owner chat ID and owner user ID. The resulting callback remains below Telegram's 64-byte limit even for long Forge decision IDs.

On receipt Forge validates:

1. callback/update structure;
2. exact Telegram `from.id` owner allowlist;
3. exact private `message.chat.id` owner allowlist;
4. callback length and structure;
5. callback HMAC;
6. exactly one locally registered notification matching the hashed decision key;
7. that the registered notification is mobile-safe;
8. that the actual Forge decision still exists and is OPEN;
9. DEFER against the persisted classification;
10. the action through the local Forge governance API.

The callback cannot grant capabilities. It only asks the existing governance API to apply one owner-decision transition.

## Restart/replay handling

Local delivery state is stored at `/var/lib/forge-telegram/state.json` by default:

- next Telegram `update_id` offset;
- registered mobile/restricted decision notifications and message IDs;
- a bounded set of recently processed callback-query IDs;
- last daily-digest date.

The state file is written atomically and mode 0600. The Telegram offset advances only after an update is handled. A crash before acknowledgement therefore retries instead of silently dropping an owner action. YES/NO are additionally protected by the governance API's resolved-decision state.

## Daily digest

At the configured local hour (19:00 Europe/London in the example), the adapter sends one compact digest:

- up to eight registered mobile-safe summaries;
- restricted gates as count-only;
- no full decision content;
- resolved/missing decisions are pruned from local notification state.

`DEFER` and `MORE INFO` keep the gate open. Their original keyboard remains usable and deferred gates reappear in the daily digest. YES/NO resolve the decision and clear the inline keyboard.

## Secrets

The systemd unit uses `LoadCredential=` for:

- `telegram-bot-token`;
- `forge-control-key`;
- `telegram-callback-hmac-key` (hex, at least 32 bytes);
- `telegram-notify-api-key` (at least 32 characters).

None belongs in the environment file, repository, Task Capsule or Hand. Non-secret settings are owner IDs, local API URL, state/socket paths and digest settings.

Transport errors are sanitized so exceptions do not echo the Telegram Bot API URL, which embeds the bot token.

## Deployment

```bash
sudo useradd --system --home /nonexistent --shell /usr/sbin/nologin forge-telegram || true
sudo install -d -m 0700 /etc/forge/secrets
sudo install -m 0600 /path/to/telegram-bot-token /etc/forge/secrets/telegram-bot-token
sudo install -m 0600 /path/to/forge-control-key /etc/forge/secrets/forge-control-key
openssl rand -hex 32 | sudo tee /etc/forge/secrets/telegram-callback-hmac-key.hex >/dev/null
openssl rand -hex 32 | sudo tee /etc/forge/secrets/telegram-notify-api-key >/dev/null
sudo chmod 0600 /etc/forge/secrets/telegram-*.key /etc/forge/secrets/telegram-*.hex 2>/dev/null || true

sudo install -m 0644 infra/telegram/telegram-governance.env.example /etc/forge/telegram-governance.env
sudoedit /etc/forge/telegram-governance.env
sudo install -m 0644 infra/telegram/forge-telegram-governance.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now forge-telegram-governance
```

The governance channel must be the owner's private chat with the bot. Both `FORGE_TELEGRAM_OWNER_USER_ID` and `FORGE_TELEGRAM_OWNER_CHAT_ID` are checked; do not use a shared group for owner gates.

The trusted Brain-side caller sends a notification to `/run/forge-telegram/notify.sock` only after it has decided what summary, if any, is safe to disclose externally. Wiring that call directly into decision creation is a deployment/integration step; it is intentionally not available to ordinary Hands.

## Required live Reality Anchors

Before using Telegram for real owner gates, prove:

1. a mobile-safe test gate renders only the approved summary;
2. a restricted gate sends no sensitive content and no action buttons;
3. wrong user, wrong chat and tampered callback are denied without a governance action;
4. YES/NO change exactly one expected decision and clear its keyboard;
5. L3 omits DEFER;
6. restart resumes from the persisted update offset without replaying an applied decision;
7. daily digest includes only approved mobile-safe summaries plus restricted counts;
8. bot token, Forge control key, callback key and notification transport key are absent from process arguments, project workspaces, logs and Hand environments.
