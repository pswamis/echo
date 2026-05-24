# Echo — Roadmap & Feature Ideas

Living list of features and improvements for the Echo fork beyond the
Dograh upstream. Loosely ranked by impact-per-hour. Cross items off
or re-order as you go.

## Top 3 next picks

1. **Custom Kokoro voice selection** (#1 below) — 5 min, immediately demoable
2. **n8n webhook integration on call complete** (#4) — ~30 min, best ROI for
   wiring Echo into the rest of your homelab
3. **Mobile-friendly UI** (#5) — 3-5 hr, your original motivation for the
   source fork; pays off every phone interaction

---

## Backlog

### 1. Custom Kokoro voice ⭐
- [ ] List available voices from the local Speaches/Kokoro endpoint
- [ ] Pick a voice that isn't the default `af_heart` (try `am_michael`, `bf_emma`)
- [ ] Update TTS config in `user_configurations.tts.voice`

**Effort:** 5 min. **Why:** Trivially more personalized; demos better.

### 2. Outbound calling ⭐
- [ ] Verify a caller ID in Twilio Console (trial requires this)
- [ ] Wire up a workflow to dial out via Dograh's outbound mode
- [ ] Test with an appointment-reminder script or similar

**Effort:** ~30 min plus Twilio verification step.
**Why:** You already have Twilio + a working bot; outbound unlocks a whole
class of use cases (reminders, surveys, follow-ups).
**Related schema:** `campaigns` table exists for batch outbound.

### 3. Workflow templates / prompt library
- [ ] Save reusable agent personas (lead screener, appointment confirmer,
  call-quality tester, etc.) as templates
- [ ] Expose template gallery in the workflow creation flow
- [ ] Clone-from-template instead of generating from scratch each time

**Effort:** 1-2 hr. **Why:** As you build more agents, regenerating from
description gets stale. Templates lock in good prompts.

### 4. n8n webhook on call complete ⭐
- [ ] Un-pause the existing n8n install
- [ ] In Dograh: configure a workflow-integration webhook that fires on
  call end with `{transcript, summary, run_id, duration, cost}`
- [ ] n8n routes it: Slack ping, Linear ticket, email digest, whatever fits

**Effort:** ~30 min — most of it on the n8n side. No Echo code changes.
**Why:** Best single hour you can spend; makes the voice agent part of
your homelab fabric instead of an isolated tool.

### 5. Mobile-friendly UI ⭐
- [ ] Audit existing `hidden md:flex` / `md:hidden` Tailwind breakpoints
- [ ] Fix the workflow editor (currently desktop-canvas; needs touch-friendly
  alternative — or hide editor on mobile and only allow run/observe)
- [ ] Test on iPhone Safari + Android Chrome
- [ ] Bottom-sheet patterns where modals don't fit

**Effort:** 3-5 hr depending on how deep. **Why:** Your original motivation
for the source fork. Pays off every time you open it on a phone.

### 6. Live transcription view during a call
- [ ] Subscribe to the WebSocket signaling stream from the workflow run page
- [ ] Render the running ASR transcript on the side
- [ ] Optionally show LLM tool calls as they happen

**Effort:** ~3 hr. **Why:** Demos really well, and is genuinely useful for
debugging bad turns in real time.

### 7. Knowledge base for the bot
- [ ] Use existing `/files` upload + `knowledge-base/documents` API
- [ ] Wire RAG so the bot can answer from your uploaded docs
- [ ] Workflow editor: per-node toggle for "use knowledge base"

**Effort:** ~half day. **Why:** Turns the bot into a domain-specific
expert without prompt-engineering everything inline.

### 8. Cloudflare Access in front of echo.pscloud.dev
- [ ] In Cloudflare Zero Trust, add an Access application for
  `echo.pscloud.dev` (and `dograh-api.pscloud.dev` if you keep that)
- [ ] Email or Google SSO; whitelist your own emails
- [ ] Keep the existing `/auth/login` as a secondary gate

**Effort:** 15 min. **Why:** Defense-in-depth if you ever share the URL.
The OSS edition's built-in auth is fine, but a second layer is free.

### 9. Multi-language voice
- [ ] Swap `Systran/faster-distil-whisper-large-v3` → multilingual
  `Systran/faster-whisper-large-v3` (full, ~1.5 GB more VRAM)
- [ ] Add non-English Kokoro voices (Hindi `hf_*`, Spanish `ef_*`, etc.)
- [ ] Verify VRAM budget still fits with qwen2.5:3b LLM

**Effort:** 30 min model swap, plus testing. **Why:** Opens the bot to
non-English callers. Important if you ever serve UAE-local users (Arabic).

### 10. Drop Twilio trial pre-roll
- [ ] Upgrade Twilio account ($20 minimum top-up)
- [ ] Re-test inbound — the "this is a trial account" message disappears

**Effort:** 5 min after deciding to spend $20. **Why:** Cosmetic but
kills demo polish. Worth it before showing to non-technical audiences.

---

## Stretch ideas (lower confidence on ROI)

- **A/B testing different prompts per node** — version control built into
  workflow editor with a diff view
- **Voice clone for personal use** — XTTS-v2 or F5-TTS to generate a
  custom voice that sounds like *you* (legally fine if it's your own voice,
  gets weird otherwise)
- **Call analytics dashboard** — graphs of duration, common intents,
  drop-off rates by workflow node
- **Operator handoff** — bot transfers to a real number when it can't
  resolve (Twilio supports `<Dial>` from a webhook response)
- **WhatsApp / Telegram async bot** — separate from voice but uses the
  same workflow engine for text-based interaction. See earlier session
  notes; would handle UAE callers who can't easily reach an international
  number.

---

## Done

- [x] **Initial Echo rebrand** (Dograh → Echo across UI source, favicon swap)
- [x] **Remove "Echo Model Credits" card** from /usage (deleted at source)
- [x] **Remove Slack + GitHub Star badge** from app header
- [x] **Update workflow prompts** to focus on voice agent call quality testing

---

## Infrastructure debt to address before scaling

These aren't features but matter if you ever push this beyond personal use:

- **Move docker storage to NVMe** — currently on the 8 TB HDD, kills build
  speed (~30-60 min source builds, IO contention with running apps).
  Boot pool's Samsung 980 has plenty of room. ~30 min one-time migration.
- **Cellular reachability for Web Call** without IPv6 — would need router
  UDP port-forward for coturn, plus `turn.pscloud.dev` as DNS-only A
  record at public IP. Currently relies on Etisalat IPv6 working for
  cellular WebRTC peer-to-peer.
- **Backup strategy** — `My8TBPool` is single-disk, no real backups beyond
  the `BIGSMB` 1-week snapshots. Postgres + AppConfig snapshots help but
  pool failure = full loss. Mirror? Cloud backup of the postgres dump?
