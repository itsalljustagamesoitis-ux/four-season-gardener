#!/bin/bash
set -e
cd /Users/keithlacy/four-season-gardener

BATCH=30
TOTAL=189

for start in $(seq 0 $BATCH $TOTAL); do
  echo "=== Batch starting at offset $start ==="
  python3 producer/fsg-producer.py --count $BATCH --publish
  
  COUNT=$(ls content/articles/*.md | wc -l | tr -d ' ')
  git add content/articles/ data/pipeline.json data/pipeline.json.bak
  git commit -m "Publish batch: $COUNT articles live" || echo "Nothing new to commit"
  git push origin main
  echo "=== Pushed. $COUNT articles live. ==="
done

echo "All done."
