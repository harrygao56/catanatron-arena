# catanatron-arena replay UI

Standalone replay viewer for Catanatron Arena games. Reads JSON artifacts
produced by `catanatron-arena run` (see `runs/<run>/games/<id>/`).

## Develop

```bash
cd replay-ui
npm install
# symlink runs/ into public/data so the dev server can fetch artifacts
ln -s ../../runs public/data
# (re)build the index of runs / games
python3 scripts/build_replay_index.py ../runs public/data
npm run dev
```

Open http://localhost:5180.

## Data layout it expects

```
public/data/                 (symlink to repo runs/)
  index.json                 list of runs
  <run>/index.json           list of games in that run
  <run>/games/<id>/
    viewer.json              timeline summary (per decision)
    states/state_NNNNNN.json full game state at that step
    decisions/decision_NNNNNN.json   full decision detail incl. agent trace
```
