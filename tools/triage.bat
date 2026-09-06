@echo off
REM Premiere moitie du pipeline : nettoyage clapcrate + nettoyage tags + analyse
REM Essentia + classement dans le bon bac, sur les fichiers deposes dans
REM 00_AZURACAST\_incoming.
REM
REM CE SCRIPT NE MET RIEN EN LIGNE. Depuis la separation du 2026-09-05, il
REM classe et s'arrete : le verdict d'antenne (trop energique ? trop repetitif ?
REM trop loin de la house ?) et l'envoi AzuraCast appartiennent a analyse.bat.
REM Un morceau envoye peut passer a l'antenne dans les minutes qui suivent --
REM garder l'envoi derriere le verdict est ce qui garantit que rien n'atteint
REM la radio sans avoir ete note.
REM
REM Double-clique ce fichier, puis analyse.bat.

echo === KALBASSFM - Pipeline, etape 1/2 : classement ===
echo.

echo === Phase 0 : Nettoyage CLAPCRATE.COM de la bibliotheque existante ===
python "%~dp0clean_clapcrate_full.py" --apply
echo.

echo === Phase 1 : Triage des nouveaux morceaux ===
echo.

wsl -e bash -c "source ~/essentia-env/bin/activate && python3 '/mnt/c/Users/ph.dufourcq/Documents/0_Claude Code/3_Radiofm/tools/triage_new_tracks.py'"

REM La table BPM du jeu chat live (api/bpm-table.json) n'est plus regeneree ici :
REM elle doit rester alignee sur metadata.json, or un verdict d'analyse peut
REM encore en retirer un morceau. C'est analyse_new_tracks.py, en fin de
REM pipeline, qui la regenere -- c'est le decalage entre les deux fichiers qui a
REM rendu le jeu muet deux fois (2026-07-28 et 2026-09-04). Pour la regenerer
REM seule :
REM     python tools\export_bpm_table.py

echo.
echo === Etape 1/2 terminee ===
echo.
echo Les morceaux sont classes dans leur bac, mais PAS a l'antenne.
echo ETAPE SUIVANTE : analyse.bat -- juge chaque titre, met en ligne ce qui
echo passe, regenere la table BPM du chat live.
pause
