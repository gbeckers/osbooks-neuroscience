# background topic reader definitions


## Sources:

- https://github.com/openstax/osbooks-college-algebra-bundle upstream_commit (2026-07-09; commit 789b540)
  - included modules alg-adapt-m49363
  

## 

## Build and compile document

```sh
python3 tools/validate.py reader/topics_background/topics-background.collection.xml
python3 tools/build_latex.py reader/topics_background/topics-background.collection.xml \
--margin="1in" \
--out build/topics_background/background_topics.tex
cd build/topics_background/ && xelatex background_topics.tex && xelatex background_topics.tex
cd ../../
```
