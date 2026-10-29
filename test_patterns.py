"""Offline tests for the historical encounter checker; no network calls."""
from __future__ import annotations
from types import SimpleNamespace
from pattern_checker import analyze_match_history, scan_players, demo_reports

ME = 'my-puuid'
OPPONENT = 'repeat-opponent'

def v3_match(i, *, repeat=True, win=True, match_id=None):
    players = [
        {'puuid': ME, 'team': 'Blue'},
        {'puuid': f'ally-{i}', 'team': 'Blue'},
        {'puuid': OPPONENT if repeat else f'opponent-{i}', 'team': 'Red'},
        {'puuid': f'other-{i}', 'team': 'Red'},
    ]
    return {'metadata': {'matchid': match_id or f'match-{i}', 'mode': 'Competitive'},
            'players': {'all_players': players},
            'teams': {'blue': {'has_won': win}, 'red': {'has_won': not win}}}

matches = [v3_match(i, repeat=(i in (0, 1, 3, 7)), win=i%2==0) for i in range(10)]
report = analyze_match_history('MyPlayer', ME, matches)
assert report.status == 'complete' and report.checked == 10
assert len(report.findings) == 1, report
assert report.findings[0].encounters == 4
assert report.findings[0].player_wins == 1 and report.findings[0].player_losses == 3
assert OPPONENT not in report.findings[0].label

# Duplicate match does not increment count or produce false positives.
duplicates = [v3_match(i, repeat=(i in (0, 1, 2))) for i in range(10)] + [v3_match(1)]
result = analyze_match_history('Me', ME, duplicates)
assert result.checked == 10 and not result.findings

# Four encounters with the opponent on OUR side count as zero opposing encounters.
same_side = [v3_match(i, repeat=i < 4) for i in range(10)]
for m in same_side[:4]:
    m['players']['all_players'][2]['team'] = 'Blue'
result = analyze_match_history('Me', ME, same_side)
assert not result.findings

# Older v4 flat schema, with optional team result list.
v4 = []
for i in range(10):
    v4.append({'metadata': {'match_id': f'v4-{i}', 'queue_id': 'competitive'},
               'players': [{'puuid': ME, 'team_id': 'Blue'},
                           {'puuid': OPPONENT if i < 5 else f'different-{i}', 'team_id': 'Red'}],
               'teams': [{'team_id': 'Blue', 'won': True}, {'team_id': 'Red', 'won': False}]})
r = analyze_match_history('Me', ME, v4)
assert r.checked == 10 and len(r.findings) == 1 and r.findings[0].encounters == 5

# Partial, unavailable, inappropriate mode.
partial = analyze_match_history('Me', ME, [v3_match(1), v3_match(2)])
assert partial.status == 'partial' and partial.checked == 2
assert analyze_match_history('Me', ME, []).status == 'unavailable'
assert analyze_match_history('Me', ME, [{'metadata':{'matchid':'x','mode':'Deathmatch'}, 'players':{}}]).checked == 0

# Scans selected players once; fake API used instead of live HenrikDEV.
calls=[]
def fake_api(url, key, params):
    calls.append((url,params))
    return {'data': matches}
players = [SimpleNamespace(name='MyPlayer', puuid=ME)]
results = scan_players(players, 'test-key', 'na', fake_api)
assert len(calls)==1 and calls[0][1] == {'mode':'competitive','size':10}
assert len(results)==1 and results[0].findings[0].encounters==4
assert demo_reports()[0].findings[0].encounters==5

# Existing features remain intact.
from backend import KNOWN_AGENTS, demo_snapshot, estimate_match, AgentLockService
s = demo_snapshot()
assert len(KNOWN_AGENTS) >= 29
assert len(s.allies) == len(s.enemies) == 5
assert estimate_match(s.allies, s.enemies)[0] is not None
assert hasattr(AgentLockService, 'lock_agent') and hasattr(AgentLockService, 'select_agent')
print('PASS: v3/v4 histories, dedup, opposing-only matching, thresholds, partial histories, async API fixture, old features')
