# Design System — Smart Strength Coach

## Product Context
- **What this is:** A strength training coach app for squat/bench/deadlift with video-based analysis.
- **Who it’s for:** Intermediate lifters and powerlifting-style trainees who want objective feedback and a plan loop.
- **Core loop:** Record set → upload → async analysis → report with time-coded evidence → next-session adjustments.

## Aesthetic Direction
- **Direction:** Industrial / Utilitarian (trust-first)
- **Decoration level:** Minimal (data carries the personality)
- **Mood:** Calm, precise, coach-notes vibe. No hype; everything looks measurable.

## Typography
Design goal: strong numeric legibility and clear hierarchy without “generic SaaS.”

- **Display / Headlines:** Space Grotesk (600)
- **Body / UI:** IBM Plex Sans (400/500)
- **Data / Metrics:** IBM Plex Mono (400/500, tabular feel)

**Scale (px / line-height):**
- `display-xl` 28 / 34 (Semibold)
- `title-lg` 20 / 26 (Semibold)
- `title-md` 16 / 22 (Medium)
- `body` 15 / 22 (Regular)
- `caption` 12 / 16 (Regular)

## Color
**Approach:** Restrained. One accent + semantic colors. Surfaces carry hierarchy, not gradients.

### Dark tokens (default)
- `bg/0` #0B0F14
- `bg/1` #101723
- `surface/0` #131C2A
- `surface/1` #172235
- `border/0` #223149
- `text/primary` #EAF0FA
- `text/secondary` #A9B4C7
- `text/tertiary` #7E8AA1
- `accent/primary` #3B82F6
- `success` #22C55E
- `warn` #F59E0B
- `danger` #EF4444

### Light tokens (secondary)
- `bg/0` #F7FAFF
- `bg/1` #EEF4FF
- `surface/0` #FFFFFF
- `surface/1` #F3F6FF
- `border/0` #D6E2F2
- `text/primary` #0B1220
- `text/secondary` #3C4A63
- `text/tertiary` #647391
- `accent/primary` #2563EB
- `success` #16A34A
- `warn` #D97706
- `danger` #DC2626

### Severity mapping
- `severity/high` → `danger`
- `severity/med` → `warn`
- `severity/low` → `accent/primary`

## Spacing
- **Base unit:** 4px
- **Density:** Comfortable (data-dense pages may use compact variants)
- **Scale:** 4, 8, 12, 16, 20, 24, 32, 48

## Layout
- **Type:** App UI (not marketing)
- **Navigation:** 4-tab bottom nav: Training / Analysis / Plan / Profile
- **Card policy:** Cards must be functional (status, finding, prescription). No decorative card mosaics.
- **Report hierarchy:** Top3 detailed findings first; full list collapsed by default.

## Motion
- **Approach:** Minimal-functional.
- **Durations:** micro 80–120ms; short 160–220ms; medium 260–360ms
- **Easing:** enter `ease-out`; exit `ease-in`; move `ease-in-out`

## Accessibility Baselines
- Touch targets ≥ 44px.
- Status is never color-only (text labels required).
- Time-coded evidence uses both `mm:ss-mm:ss` and highlight in playback.

## Decisions Log
| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-03-24 | Industrial/utilitarian + restrained palette | Builds trust; data-first UI |
| 2026-03-24 | Space Grotesk + IBM Plex Sans/Mono | Distinct but readable; strong metrics |