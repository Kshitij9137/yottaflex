setup:    ; pip install -r requirements.txt
test:     ; pytest -q
starter:  ; python -m yottaflex.generate --n-employees 1000  --out data/starter
full:     ; python -m yottaflex.generate --n-employees 10000 --out data/full
validate: ; python -m yottaflex.validate --data data/full --report docs/validation_summary.md