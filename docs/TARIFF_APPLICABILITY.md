# Check Kraken applicable rates

Run the packaged diagnostic from the directory containing the private deployment's Compose file. Use a UK date with known charging activity if you want to investigate whether returned intervals align with EV charging.

```sh
docker compose exec -T octopusmcp python check_applicable_rates.py 2026-11-08
```

With Docker alone, run the diagnostic inside the `octopusmcp` container. The shell saves the summary on the host and displays errors in the terminal.

```sh
docker exec octopusmcp python /app/check_applicable_rates.py 2026-11-08 \
  > applicable-rates-2026-11-08.json
```

The diagnostic uses the running container's configured account and key. It selects the account's sole electricity import supply point. Multiple meter serials at that point are supported because Kraken takes a supply-point identifier. If several import supply points exist, the diagnostic stops before the GraphQL token exchange.

The output reports counts for the first page of up to 100 rows, including distinct values, half-hour intervals, overlaps, rows outside the selected day, and how many minutes the returned intervals cover. If `has_more_pages` is true, coverage describes the first page only. An empty page confirms query access for the sample but leaves applicability unverified. A token-exchange error and an error from the subsequent query are reported separately.

The `minutes_with_multiple_distinct_values` count measures how long two or more different numeric values coincide within the selected UK day on the first page. Each minute counts once even when three rows overlap. Equal prices and rows that only touch at an endpoint contribute zero. A positive count leaves rate precedence unresolved.

The schema describes the response as rates applicable to an account and meter point over a time period. Verify the semantics against a known tariff change or charging period and corroborate the units and VAT basis with Octopus before using the values in a cost calculation. The aggregate output contains no meter identifiers, tokens, raw prices, or individual interval timestamps.

## Live check on 18 November 2026

An authenticated query for one UK day returned four rows on a single page. All four intersected the day and had valid bounds and values. There were two distinct values and zero 30-minute rows. The union of the returned intervals covered all 1,440 minutes, and three rows started before an earlier row ended.

## Follow-up overlap measurement

The operator reported four valid rows on a single page for one UK day. The diagnostic counted two distinct values and 1,440 minutes with multiple distinct values across a 1,440-minute day. Both values therefore covered every minute of the sample. The summary omitted the sample date.

Interval timing alone leaves both values as candidates throughout the day. Identifying the billed rate requires independent evidence, such as an itemised statement for a known period. The rate units, VAT basis and connection to EV dispatch also remain unverified.
