<#
.SYNOPSIS
  Retrouve les morceaux listes dans des exports Rekordbox (.txt) au sein d'une
  bibliotheque musicale locale, et les copie a cote de chaque .txt.

.DESCRIPTION
  Chaque .txt est un export Rekordbox tabule (colonnes "Titre du morceau" et
  "Artiste" entre autres). Ce script :
    1. Indexe une seule fois la bibliotheque musicale (recursif).
    2. Trouve tous les .txt sous -PlaylistsRoot (recursif).
    3. Pour chaque morceau, cherche le meilleur fichier audio correspondant.
    4. Par defaut (dry-run) : affiche un rapport sans rien copier.
       Avec -Copier : copie reellement les fichiers a cote de leur .txt.

.PARAMETER PlaylistsRoot
  Dossier parent contenant les sous-dossiers playlists, chacun avec son .txt.

.PARAMETER MusicLibrary
  Racine de recherche recursive des fichiers audio (defaut: bibliotheque Rekordbox).

.PARAMETER Copier
  Sans ce switch : dry-run (rapport seul, rien n'est copie).
  Avec ce switch : copie reellement les fichiers.

.EXAMPLE
  .\import-rekordbox.ps1 -PlaylistsRoot "C:\Radio\media"
  .\import-rekordbox.ps1 -PlaylistsRoot "C:\Radio\media" -Copier
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$PlaylistsRoot,

    [string]$MusicLibrary = "C:\Users\ph.dufourcq\Music",

    [switch]$Copier
)

$ErrorActionPreference = 'Stop'

$AudioExtensions = @('.mp3', '.wav', '.flac', '.aiff', '.aif', '.m4a')
$ScoreAutoMatch  = 0.80   # score mini pour une copie automatique
$ScoreAmbiguous  = 0.55   # score mini pour lister en "ambigu" (sinon introuvable)
$ScoreCloseGap   = 0.08   # ecart max entre 1er et 2e candidat pour rester "sur"

function Normalize-Text {
    param([string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) { return '' }
    $t = $Text.ToLowerInvariant()
    $t = $t -replace '\.[a-z0-9]{2,4}$', ''      # extension eventuelle
    $t = $t -replace "[\[\]\(\)\{\}\-_.,;:!?'""&/\\]", ' '
    $t = $t -replace '\s+', ' '
    return $t.Trim()
}

function Get-Tokens {
    param([string]$Text)
    $norm = Normalize-Text $Text
    if ($norm -eq '') { return @() }
    return $norm -split ' ' | Where-Object { $_.Length -gt 1 }
}

function Get-MatchScore {
    param([string[]]$TargetTokens, [string]$CandidateNormalized)
    if ($TargetTokens.Count -eq 0) { return 0 }
    $found = 0
    foreach ($tok in $TargetTokens) {
        if ($CandidateNormalized -like "*$tok*") { $found++ }
    }
    return [double]$found / [double]$TargetTokens.Count
}

function Read-RekordboxTxt {
    param([string]$Path)
    # ReadAllLines detecte automatiquement le BOM (UTF-16 typique de Rekordbox sous Windows)
    $lines = [System.IO.File]::ReadAllLines($Path)
    if ($lines.Count -lt 2) { return @() }

    $headers = $lines[0] -split "`t"
    $idxTitle  = [array]::IndexOf($headers, 'Titre du morceau')
    $idxArtist = [array]::IndexOf($headers, 'Artiste')
    if ($idxTitle -lt 0) { $idxTitle = [array]::IndexOf($headers, 'Titre') }

    if ($idxTitle -lt 0 -or $idxArtist -lt 0) {
        Write-Warning "  [$Path] colonnes 'Titre du morceau'/'Artiste' introuvables dans l'en-tete, fichier ignore."
        return @()
    }

    $rows = @()
    for ($i = 1; $i -lt $lines.Count; $i++) {
        if ([string]::IsNullOrWhiteSpace($lines[$i])) { continue }
        $cols = $lines[$i] -split "`t"
        if ($cols.Count -le [Math]::Max($idxTitle, $idxArtist)) { continue }
        $title  = $cols[$idxTitle].Trim()
        $artist = $cols[$idxArtist].Trim()
        if ($title -eq '' -and $artist -eq '') { continue }
        $rows += [PSCustomObject]@{ Title = $title; Artist = $artist }
    }
    return $rows
}

# ── 1. Indexation de la bibliotheque musicale (une seule fois) ──
Write-Host "Indexation de la bibliotheque musicale : $MusicLibrary ..." -ForegroundColor Cyan
if (-not (Test-Path $MusicLibrary)) {
    throw "Bibliotheque musicale introuvable : $MusicLibrary"
}
$libraryFiles = Get-ChildItem -Path $MusicLibrary -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object { $AudioExtensions -contains $_.Extension.ToLowerInvariant() }

$index = @()
foreach ($f in $libraryFiles) {
    $index += [PSCustomObject]@{
        File       = $f
        Normalized = Normalize-Text $f.BaseName
    }
}
Write-Host "  -> $($index.Count) fichiers audio indexes." -ForegroundColor Cyan
Write-Host ""

# ── 2. Trouver tous les .txt sous PlaylistsRoot ──
if (-not (Test-Path $PlaylistsRoot)) {
    throw "Dossier de playlists introuvable : $PlaylistsRoot"
}
$txtFiles = Get-ChildItem -Path $PlaylistsRoot -Recurse -Filter '*.txt' -File |
    Where-Object { $_.Name -ne '_rapport_import.txt' }

if ($txtFiles.Count -eq 0) {
    Write-Warning "Aucun fichier .txt trouve sous $PlaylistsRoot"
    return
}

$modeLabel = if ($Copier) { 'COPIE REELLE' } else { 'DRY-RUN (aucun fichier ne sera copie)' }
Write-Host "Mode : $modeLabel" -ForegroundColor Yellow
Write-Host ""

$globalCopied = 0
$globalPresent = 0
$globalAmbiguous = 0
$globalMissing = 0

foreach ($txt in $txtFiles) {
    $destDir = $txt.DirectoryName
    Write-Host "=== $($txt.FullName) ===" -ForegroundColor Green
    Write-Host "    Destination : $destDir"

    $tracks = Read-RekordboxTxt -Path $txt.FullName
    if ($tracks.Count -eq 0) {
        Write-Host "    (aucune piste lue)" -ForegroundColor DarkGray
        Write-Host ""
        continue
    }

    $reportLines = @()
    $reportLines += "Rapport d'import Rekordbox - $($txt.Name)"
    $reportLines += "Genere le $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
    $reportLines += "Mode : $modeLabel"
    $reportLines += ""

    foreach ($track in $tracks) {
        $targetTokens = @(Get-Tokens $track.Title) + @(Get-Tokens $track.Artist)
        $targetTokens = $targetTokens | Select-Object -Unique

        $scored = foreach ($entry in $index) {
            [PSCustomObject]@{
                Entry = $entry
                Score = Get-MatchScore -TargetTokens $targetTokens -CandidateNormalized $entry.Normalized
            }
        }
        $ranked = $scored | Where-Object { $_.Score -ge $ScoreAmbiguous } | Sort-Object -Property Score -Descending

        $label = "$($track.Artist) - $($track.Title)".Trim(' -')
        $line = ''

        if ($ranked.Count -eq 0) {
            $line = "INTROUVABLE   $label"
            $globalMissing++
        }
        else {
            $best = $ranked[0]
            $secondScore = if ($ranked.Count -gt 1) { $ranked[1].Score } else { 0 }
            $isClear = ($best.Score -ge $ScoreAutoMatch) -and (($best.Score - $secondScore) -ge $ScoreCloseGap -or $ranked.Count -eq 1)

            # Faux positif frequent : plusieurs candidats a egalite ne sont en
            # fait que le meme morceau en double (meme nom, ou juste .mp3/.wav).
            # Dans ce cas, pas vraiment ambigu -> on choisit, en preferant .mp3.
            if (-not $isClear -and $best.Score -ge $ScoreAutoMatch) {
                $tied = $ranked | Where-Object { $_.Score -ge $best.Score - 0.001 }
                $tiedBaseNames = $tied | ForEach-Object { $_.Entry.Normalized } | Select-Object -Unique
                if ($tiedBaseNames.Count -eq 1) {
                    $preferred = $tied | Sort-Object -Property @{ Expression = { if ($_.Entry.File.Extension -eq '.mp3') { 0 } else { 1 } } }, @{ Expression = { $_.Entry.File.FullName.Length } } | Select-Object -First 1
                    $best = $preferred
                    $isClear = $true
                }
            }

            if (-not $isClear) {
                $candidates = ($ranked | Select-Object -First 3 | ForEach-Object { "$($_.Entry.File.Name) ($([Math]::Round($_.Score,2)))" }) -join ' | '
                $line = "AMBIGU        $label  ->  $candidates"
                $globalAmbiguous++
            }
            else {
                $srcFile = $best.Entry.File
                $destPath = Join-Path $destDir $srcFile.Name

                if (Test-Path $destPath) {
                    $line = "DEJA PRESENT  $label  ($($srcFile.Name))"
                    $globalPresent++
                }
                elseif ($Copier) {
                    Copy-Item -Path $srcFile.FullName -Destination $destPath -ErrorAction Stop
                    $line = "COPIE         $label  <-  $($srcFile.Name)"
                    $globalCopied++
                }
                else {
                    $line = "A COPIER      $label  <-  $($srcFile.Name)"
                    $globalCopied++
                }
            }
        }

        Write-Host "  $line"
        $reportLines += $line
    }

    $reportPath = Join-Path $destDir '_rapport_import.txt'
    $reportLines | Out-File -FilePath $reportPath -Encoding UTF8
    Write-Host "    Rapport ecrit : $reportPath" -ForegroundColor DarkGray
    Write-Host ""
}

Write-Host "=== Resume global ===" -ForegroundColor Cyan
$copiedLabel = if ($Copier) { 'Copies' } else { 'A copier (dry-run)' }
Write-Host "  $copiedLabel     : $globalCopied"
Write-Host "  Deja presents   : $globalPresent"
Write-Host "  Ambigus         : $globalAmbiguous"
Write-Host "  Introuvables    : $globalMissing"
if (-not $Copier -and $globalCopied -gt 0) {
    Write-Host ""
    Write-Host "Relancez avec -Copier pour executer les copies." -ForegroundColor Yellow
}
