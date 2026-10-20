"""Retrieval evaluation: does the knowledge search find the right card? Pure logic.

A small labeled set of questions a user might ask the coach (or the agent might need), each
with the card(s) that answer it. Several are worded without the card's own vocabulary
("phone" for screens, "coffee" for caffeine, "workout" for exercise), which is where lexical
search struggles and embeddings should help. Metrics: hit@1 and hit@3 (a relevant card in the
top 1 / top 3) and MRR (mean reciprocal rank of the first relevant card), per search mode.
"""
QUERIES = [
    ("How many hours of sleep should I get?", {"sleep-duration"}),
    ("Is six hours of sleep enough for me?", {"sleep-duration"}),
    ("Can sleeping in on the weekend make up for a bad week?", {"consistent-schedule", "sleep-duration"}),
    ("Should I go to bed at the same time every day?", {"consistent-schedule"}),
    ("How do I start going to bed earlier?", {"consistent-schedule"}),
    ("Why should I stop looking at my phone before bed?", {"evening-screens-light"}),
    ("Does scrolling Instagram at night hurt my sleep?", {"evening-screens-light"}),
    ("What should I do if I can't fall asleep?", {"evening-screens-light"}),
    ("Does bright light in the evening matter?", {"evening-screens-light"}),
    ("What temperature should my bedroom be?", {"bedroom-and-routine"}),
    ("What is a good routine before bed?", {"bedroom-and-routine"}),
    ("Is it bad to eat a big dinner late?", {"bedroom-and-routine"}),
    ("When should I have my last coffee?", {"caffeine-timing"}),
    ("Does an afternoon espresso affect my night?", {"caffeine-timing"}),
    ("Is it okay to work out at night?", {"evening-exercise"}),
    ("Will a late HIIT class ruin my sleep?", {"evening-exercise"}),
    ("How close to bedtime can I finish a hard run?", {"evening-exercise"}),
    ("I trained a lot more this week than usual, is that a problem?", {"training-load"}),
    ("What is the acute chronic workload ratio?", {"training-load"}),
    ("Does ramping up mileage quickly raise injury risk?", {"training-load"}),
    ("My HRV dropped this morning, should I worry?", {"hrv-trends"}),
    ("Why does my heart rate variability jump around so much?", {"hrv-trends"}),
    ("Can I compare my HRV with my friend's?", {"hrv-trends"}),
    ("What does 'below your normal range' mean?", {"rl-baselines"}),
    ("How is my baseline calculated?", {"rl-baselines"}),
    ("How do you know how much sleep I need?", {"rl-baselines", "sleep-duration"}),
    ("Why won't you suggest an intense workout today?", {"rl-safety"}),
    ("When is a hard session ruled out?", {"rl-safety"}),
    ("How do the experiments decide if a habit worked?", {"rl-experiments"}),
    ("Why did my experiment come out inconclusive?", {"rl-experiments"}),
]


def evaluate(index, mode: str, k: int = 3) -> dict:
    hit1 = hitk = rr = 0.0
    misses = []
    for q, relevant in QUERIES:
        ranked = [c.card for c in index.search(q, k=len(index.chunks), mode=mode)]
        seen, order = set(), []
        for card in ranked:                 # rank cards, not chunks
            if card not in seen:
                seen.add(card)
                order.append(card)
        first = next((i for i, card in enumerate(order) if card in relevant), None)
        hit1 += first == 0
        hitk += first is not None and first < k
        rr += 1.0 / (first + 1) if first is not None else 0.0
        if first is None or first >= k:
            misses.append(q)
    n = len(QUERIES)
    return dict(mode=mode, queries=n, hit_at_1=round(hit1 / n, 3), hit_at_k=round(hitk / n, 3), k=k,
                mrr=round(rr / n, 3), misses=misses)
