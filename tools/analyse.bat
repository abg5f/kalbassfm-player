@echo off
REM Seconde moitie du pipeline d'ingestion : JUGER les morceaux que triage.bat a
REM classes, puis mettre en ligne ce qui passe.
REM
REM Pourquoi c'est un .bat separe et non la suite de triage.bat : un morceau
REM envoye sur AzuraCast peut passer a l'antenne dans les minutes qui suivent.
REM Tant que ce script n'a pas tourne, RIEN de ce que le triage a classe n'est
REM en ligne -- c'est la garantie que rien n'atteint la radio sans avoir ete note.
REM
REM Pas de WSL ici : aucune re-analyse Essentia (les descripteurs sont deja dans
REM metadata.json), le script relit des nombres. Quelques secondes.
REM
REM Double-clique ce fichier apres triage.bat.

echo === KALBASSFM - Analyse d'antenne ===
echo.

echo --- Verdicts (simulation, rien n'est deplace ni envoye) ---
python "%~dp0analyse_new_tracks.py"
if errorlevel 1 goto :fin

echo.
set "REP="
set /p REP="Appliquer ces verdicts et mettre en ligne ? (o/N) "
if /i not "%REP%"=="o" goto :annule

echo.
echo --- Application ---
python "%~dp0analyse_new_tracks.py" --apply
goto :fin

:annule
echo.
echo Annule -- rien n'a bouge. Les morceaux restent en file d'attente.
echo   Pour ecarter aussi les "a ecouter" :
echo       python tools\analyse_new_tracks.py --apply --strict
echo   Pour renvoyer un titre ecarte a tort dans le pipeline :
echo       python tools\analyse_new_tracks.py --requeue "nom du fichier.mp3"

:fin
echo.
echo === Termine ===
pause
