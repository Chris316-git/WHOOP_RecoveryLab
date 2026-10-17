# Privacy Policy

**Recovery Lab** · Effective date: October 16, 2026

Recovery Lab is an open-source tool that analyzes your own wearable and calendar data to
run personal (N-of-1) experiments and send you a daily summary. This policy explains what
data it handles, where that data lives, and how to remove it.

Recovery Lab is currently **self-hosted**: whoever runs it (the "operator") connects their
own database, email account and API credentials. If you run your own copy, you are the
operator and your data never reaches the project author.

## What data is collected

### From WHOOP (read-only, with your authorization)

- **Profile:** your WHOOP user ID and first name.
- **Physiological cycles:** strain, energy expenditure (kilojoules), average and maximum heart rate.
- **Recovery:** recovery score, resting heart rate, heart rate variability (HRV), blood
  oxygen (SpO2) and skin temperature.
- **Sleep:** start and end times, time in each sleep stage, disturbances, respiratory
  rate, and sleep performance, consistency and efficiency.
- **Workouts:** sport type, strain, heart rate, energy expenditure and distance.

The unmodified WHOOP API responses for these records are also stored, so new fields can be
analyzed later without fetching the data again. The body measurement permission is
requested, but body measurements are not currently stored.

### From Google Calendar (read-only, with your authorization)

Recovery Lab stores **time blocks only**:

- each event's start and end time, whether it is all-day, whether it is marked busy or
  free, whether it repeats, and the **number** of attendees;
- your calendar's time zone setting;
- daily schedule features derived from these blocks, such as busy minutes, meeting
  minutes and the longest free block.

If you choose to, Recovery Lab also **writes** to Google Calendar, but only to a calendar it
creates for you, called "Recovery Lab". It uses the narrow `calendar.app.created` permission,
which only covers calendars the app created and their events. Events appear there only after
you tap "Add to calendar", and Undo removes them. You can hide or delete that calendar at any time.

Recovery Lab **does not store** event titles, descriptions, locations, attachments,
conference links, or the names or email addresses of attendees. Calendar IDs, which can
contain an email address, are stored only as a one-way hash.

### Your responses to suggestions, and what happened

If you use the links in the daily email, Recovery Lab stores your response (added to the
calendar, dismissed, or marked "not useful"), the time block you chose, and the ID of the
event it created. Not responding is recorded as no response. No reasons are asked for.

The next morning, Recovery Lab compares the previous day's suggestion with data it already has
(for example, that day's strain or the time you went to bed) and stores the result (done,
partly, not done) with those few numbers. Nothing new is collected for this.

These records are used only to make future suggestions fit you better. The links in the email
are signed and expire, and they contain no health data.

### Information you enter (planned)

The experiment features that are planned will store short daily check-ins (for example the
time of your last caffeine, the number of alcoholic drinks, dinner time, and whether you
were traveling or sick), plus your experiment settings. Check-ins have no free-text fields.

## How the data is used

The data is used **only** to provide Recovery Lab's features to you:

- syncing and analyzing your sleep, recovery and strain;
- comparing each day with your own historical baseline;
- finding free time in your schedule so suggestions fit around it;
- estimating the effect of habit experiments with statistical models;
- sending you a daily summary email.

Your data is **not** sold, used for advertising, used to build profiles for third parties,
or used to train machine-learning models.

Recovery Lab's use and transfer of information received from Google APIs adheres to the
[Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy),
including the Limited Use requirements.

## Where the data is stored and who can access it

- **Database:** a PostgreSQL database chosen by the operator (the reference setup uses
  Supabase). Only the operator has access to it.
- **Credentials:** WHOOP and Google access tokens are stored encrypted (Fernet: AES with
  an HMAC). The encryption key lives only in the operator's local `.env` file and in their
  GitHub Actions secrets, never in the code repository.
- **Scheduled job:** the daily sync runs on GitHub Actions. Its logs contain only status
  messages. No health or calendar values are written to them.
- **Email:** the daily summary is sent only to the address the operator configures, using
  the operator's email provider.

## Third-party services

Recovery Lab sends data only to the services needed to run it:

| Service | Purpose | Data involved |
|---|---|---|
| WHOOP API | Read your wearable data | OAuth tokens; requests for your records |
| Google Calendar API | Read your calendar's time blocks | OAuth tokens; requests for events |
| Database host (e.g. Supabase) | Storage | Everything described above |
| GitHub Actions | Run the daily job | Encrypted credentials and database connection (as secrets) |
| Email provider (e.g. Gmail) | Deliver the daily summary | The contents of the summary |
| Web host (e.g. Render) | Run the endpoint behind the email links | Database connection and keys (as secrets); your clicks |

**Language model (planned):** a later version will use the Anthropic API to word
experiment designs and explanations. Only aggregated statistics computed by Recovery Lab
would be sent, not raw records or calendar data. This policy will be updated before that
feature is turned on.

## Retention

Data is kept for as long as the operator keeps the account connected, so that long-term
personal patterns can be learned. Calendar time blocks are re-synced for a rolling window
(currently the past 365 days and the next 14 days). Events that are deleted or declined
in Google Calendar are removed on the next sync.

## How to remove your data

1. **Revoke access:**
   - Google: [myaccount.google.com/permissions](https://myaccount.google.com/permissions), then remove Recovery Lab.
   - WHOOP: remove the connected app in your WHOOP account settings.
2. **Delete stored data:** delete your rows from the database tables (every table is
   keyed by `user_id`), or delete the database project entirely.
3. **Delete credentials:** remove the `.tokens/` folder and the encryption key from
   `.env` and from GitHub Secrets.

Once access is revoked, the stored tokens stop working, even if they have not been deleted yet.

## Security

Credentials are encrypted at rest, secrets are kept out of the code repository, database
connections use TLS, and only read-only permissions are requested from WHOOP, and Google write access is limited to the app's own calendar.
No system is perfectly secure. If you find a vulnerability, please report it privately
(see Contact).

## Health information disclaimer

Recovery Lab is not a medical device and does not provide medical advice, diagnosis or
treatment. Its suggestions are general, rule-based or statistical observations about your
own data. Talk to a qualified professional about any health concern.

## Children

Recovery Lab is not intended for anyone under 18.

## Changes to this policy

Changes are published in this file, and the commit history keeps every earlier version.
The effective date at the top shows when it last changed.

## Contact

Questions or requests: open an issue at
[github.com/Chris316-git/WHOOP_RecoveryLab/issues](https://github.com/Chris316-git/WHOOP_RecoveryLab/issues).
For security reports, use GitHub's private vulnerability reporting on the repository's
Security tab.

*Recovery Lab is not affiliated with, endorsed by, or sponsored by WHOOP or Google.*
