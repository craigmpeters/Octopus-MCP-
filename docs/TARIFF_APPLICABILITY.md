# Check Kraken applicable rates

Run the packaged diagnostic from the directory containing the private deployment's Compose file. Use a UK date with known charging activity if you want to investigate whether returned intervals align with EV charging.

```sh
docker compose exec -T octopus-mcp python check_applicable_rates.py 2026-11-08
```

The diagnostic uses the running container's configured account and key. It selects the account's sole electricity import supply point. Multiple meter serials at that point are supported because Kraken takes a supply-point identifier. If several import supply points exist, the diagnostic stops before the GraphQL token exchange.

The output reports counts for the first page of up to 100 rows, including distinct values, half-hour intervals, overlaps, rows outside the selected day, and how many minutes the returned intervals cover. If `has_more_pages` is true, coverage describes the first page only. An empty page confirms query access for the sample but leaves applicability unverified. A token-exchange error and an error from the subsequent query are reported separately.

The schema describes the response as rates applicable to an account and meter point over a time period. Verify the semantics against a known tariff change or charging period and corroborate the units and VAT basis with Octopus before using the values in a cost calculation. The aggregate output contains no meter identifiers, tokens, raw prices, or individual interval timestamps.
