# Routing

## Resolution order

1. Explicit `engine` (+ optional `provider_id`) → single-candidate Route
2. Explicit `route` name/id
3. Route pinned to the calling API key
4. `is_default` Route
5. Built-in `auto` Route (all healthy available engines)

## Strategies

| Name | Behaviour |
|---|---|
| `priority` | Strict `order_index` |
| `round_robin` | Rotate start position |
| `weighted` | Weight-proportional shuffle |
| `fill_first` | Exhaust remaining quota first |
| `least_used` | Fewest recent runs |
| `least_latency` | Lowest p95 |
| `p2c` | Power of two choices |
| `random` | Uniform shuffle |
| `cost_optimised` | Cheapest first (local = 0) |
| `local_first` | Local before API |
| `quality_first` | Curated accuracy desc |
| `language_aware` | Language match first |
| `ensemble_vote` | Parallel top-k + IoU consensus |
| `auto` | Heuristic (see below) |

## Auto heuristic

- sensitive / offline → `local_first`
- handwriting hint → `quality_first` (handwriting-capable first via member filters)
- tables / structured → `quality_first`
- multi-page PDF → `cost_optimised`
- small single screenshot → `local_first` (classic engines)
- otherwise → `least_latency`

Every decision is recorded in `routing.explain`.

## Stop condition

Accept when `FileParseExitCode != -1` **and** optional `min_chars` /
`min_mean_confidence` / `require_overlay`. Otherwise keep best fallback;
if all fail, return best non-empty with `routing.degraded = true`.

## Fail-fast

`bad_input` / `unsupported_input` stop the Run immediately (one Attempt).
