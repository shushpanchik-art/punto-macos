# L2 numbers

Built on repository commit `5df564b859a0ee91145c74246550de4b836d8891` (parent of the commit that adds this file); specification rev 286. Run from `layout-corrector/audit/`.

Command: `python3 L2_recompute.py` (24 checks: parameter count of the CNN at c = 32, 64 and 96 and the multiply-adds, thresholds in nats, Poisson bounds, sizes and constants, all 36 shares of the table in 18.9 against `L6_ev1_simulation.json`).

```
OK       CNN c=64 parameters :: (3104, 6208, 20544, 12352, 387)
OK          stated: layer breakdown and total
OK       CNN c=32 -> 14,659 :: 14659
OK       CNN c=96 -> 86,915 :: 86915
OK       multiply-adds per position (c=64) = 38,912; 9-key word about 0.35 million :: (38912, 350208)
OK       FP32 size 170 KB (4 bytes per parameter) :: 170.38
OK       receptive field 1+2+4+2 = 9 (kernels 3, 5, 3)
OK       c=4: 1,584 multiply-adds per 9-key word (specified embedding), 2,880 with a 16-dimension embedding :: (1584, 2880)
OK       16-dimension embedding vs specified: 0% (c=16), 14% (c=32), 8% (c=64), 6% (c=96) fewer
OK       logit(0.999), logit(0.997), logit(0.995)
OK       example calibration lambdas en2ru :: [6.907, 5.806, 5.293]
OK       example calibration lambdas ru2en :: [6.907, 5.806, 5.293]
OK       buckets 3-4 / 5-7 / 8+
OK       4 false corrections in 100,000 is below 4.8e-5, 5 is above
OK       rule of three: 3.0e-4 for 10,000 transactions with 0 events :: 0.000299573227355399
OK       Poisson 95% upper limit for k = 0..12 (by definition of the cdf)
OK       EV-1 minimum sizes accepted, one below refused
OK       EV-1 point estimate edge: 12 events of 250,000 pass, 13 fail (4.8e-5 x 250,000 = 12)
OK       47 keys, 94 key states, token ids, vocabulary 97 :: (0, 95, 96)
OK       buffer 64, word 20 keys, undo 10 s and 100 characters, canary 300 ms, re-arm 3 pairs :: (64, 10000, 100, 300, 3)
OK       LFC1 example: pi_train shares equal their counts :: [0.38, 0.4, 0.22]
OK       w values in the allowed ranges (en) :: {'default': 0.01, 'after_switch': 0.003, 'run': 0.25}
OK       w values in the allowed ranges (ru) :: {'default': 0.01, 'after_switch': 0.003, 'run': 0.25}
OK       simulation: 36 scenario-cells x 10,000 runs, 360,000 runs checked, 0 cap violations
OK       18.9 worst false acceptance 3.3% (strong, 50 users) with upper bound 3.64% :: (0.0327, 0.036374709977720944)
OK       criteria met: false acceptance <= 5% / 7%, power >= 80%
OK       18.9 table: all 36 shares equal the JSON (rounded to 0.1%) :: 12 rows
MISMATCHES: 0
```

Result: 0 mismatches. Note: the check of section 7.5 found that the native latency column used a 16-dimension embedding for every c; the text of 7.3 and 7.5 now says so (rev 280 to 286).
