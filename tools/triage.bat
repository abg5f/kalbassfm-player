@echo off
REM Lance le pipeline complet : nettoyage clapcrate + nettoyage tags + analyse Essentia + classement
REM par creneau + regeneration de New_prog, sur les fichiers deposes dans
REM 00_AZURACAST\_incoming.
REM Double-clique ce fichier pour tout lancer d'un coup.

echo === KALBASSFM - Pipeline complet ===
echo.

echo === Phase 0 : Nettoyage CLAPCRATE.COM de la bibliotheque existante ===
python "%~dp0clean_clapcrate_full.py" --apply
echo.

echo === Phase 1 : Triage des nouveaux morceaux ===
echo.

wsl -e bash -c "source ~/essentia-env/bin/activate && python3 '/mnt/c/Users/ph.dufourcq/Documents/0_Claude Code/3_Radiofm/tools/triage_new_tracks.py'"

REM La table BPM du jeu chat live (api/bpm-table.json) est desormais regeneree
REM par triage_new_tracks.py lui-meme, en fin de run : elle reste ainsi alignee
REM sur metadata.json meme quand le triage est lance directement en WSL sans
REM passer par ce .bat -- c'est ce decalage qui a rendu le jeu muet deux fois
REM (2026-07-28 et 2026-09-04). Pour la regenerer seule :
REM     python tools\export_bpm_table.py

echo.
echo === Termine ===
echo.
echo RAPPEL : si des morceaux ont ete ajoutes, commit + push de
echo          api/bpm-table.json - sans push, le jeu BPM reste muet en ligne.
pause
