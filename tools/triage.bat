@echo off
REM Lance le pipeline complet : nettoyage tags + analyse Essentia + classement
REM par creneau + regeneration de New_prog, sur les fichiers deposes dans
REM 00_AZURACAST\_incoming.
REM Double-clique ce fichier pour tout lancer d'un coup.

echo === KALBASSFM - Triage des nouveaux morceaux ===
echo.

wsl -e bash -c "source ~/essentia-env/bin/activate && python3 '/mnt/c/Users/ph.dufourcq/Documents/0_Claude Code/3_Radiofm/tools/triage_new_tracks.py'"

echo.
echo === Termine ===
pause
