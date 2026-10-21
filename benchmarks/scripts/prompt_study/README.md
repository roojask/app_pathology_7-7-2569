# Prompt Sensitivity Study

Copy this folder to `benchmarks/scripts/prompt_study/` in the repo (any folder inside the repo works; the repo root is auto-detected).

## Run order
```
pip install jiwer scipy pandas
python run_prompt_sweep.py --split dev --limit 5      # smoke test, check the printed token counts
python run_prompt_sweep.py --split dev                # 200 cases x 10 variants (~3 h)
python analyze_prompt_sweep.py results/prompt_sweep_dev_denoiseoff.csv
# decide anything you want to change using DEV only, then freeze the prompts and run:
python run_prompt_sweep.py --split test               # 300 cases x 10 variants (~5 h)
python analyze_prompt_sweep.py results/prompt_sweep_test_denoiseoff.csv
```
Runs resume automatically if interrupted (keep the same `--out`/split/denoise).

## Check before trusting the numbers
1. The smoke test prints each variant's token count. All must be <= 223 (asserted). P5 matches P4's length.
2. `[WARN] ... example dims ... equal GT` means a few-shot example copies a test value. Change the example.
3. Sanity: P4 on the test split should land near thesis C6 (prompt on, denoise off, beam 1): WER-B about 2.6, CER_case about 7.0. If it is far off, something differs from the thesis setup (model path, audio, extractor version).
4. `--denoise off` is the default so that the prompt is the only changing factor. Re-run P0 and P4 with `--denoise on` to report the interaction.
5. DEV and TEST come from the same generator and templates. This split prevents tuning on the reported cases; it does not remove template overlap. Test set B (free-form) is still needed for that claim.
