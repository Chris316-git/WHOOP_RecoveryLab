---
id: rl-baselines
title: How Recovery Lab compares you with yourself
topic: method
source: Recovery Lab method (this project's code)
url: https://github.com/Chris316-git/WHOOP_RecoveryLab
---
Every number is compared with your own history, not with population norms. Last night's values are compared
with your median of the previous 30 days. Trends compare the last 7 days with a normal range computed from the
30 days before them; for HRV the range is computed on a log scale, because HRV is skewed, so a drop and a rise
of the same relative size count the same.

## Sleep need and shortfall
Sleep need comes from WHOOP's estimate when available, otherwise an assumed 8 hours. The weekly shortfall adds
up the minutes below that need over the last 7 nights.
