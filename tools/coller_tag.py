#!/usr/bin/env python3
"""Colle le tag « On Channel Sixteen » a la fin de chaque jingle CH-16.

POURQUOI UN SCRIPT ET PAS 51 COMMANDES A LA MAIN : le tag doit rester UN SEUL
clip, le meme partout. La meme phrase redemandee a Suno pour chaque jingle
donnerait 51 voix differentes, donc aucune signature. On produit le tag une
fois, on le colle ici.

CE QUE FAIT CHAQUE COLLAGE :
    jingle  +  court silence  +  tag       -> <sortie>/<nom du jingle>.mp3

TROIS PRECAUTIONS, dans cet ordre d'importance :

1. NIVEAU. Les clips Suno ne sortent pas tous au meme volume. Colles bruts,
   le tag arrive plus fort ou plus faible que le jingle qui le precede, et
   ca s'entend immediatement. On mesure donc la sonie (EBU R128) des deux
   fichiers et on applique un gain AU TAG SEUL pour l'aligner sur le jingle.
   Le jingle, lui, n'est jamais retouche : c'est le materiau artistique.
2. SILENCE. Colles bord a bord, la derniere syllabe du jingle mord sur le
   tag. Un souffle de 0,15 s par defaut (--gap) suffit a poser la signature.
3. FORMAT. Les fichiers Suno sont en Opus dans un conteneur .m4a : coller
   sans reencoder est impossible de toute facon (concat exige des flux
   identiques). On sort donc en MP3 320 kbps, ce qu'AzuraCast indexe sans
   discuter et ce que Mp3tag sait retagger.

Usage :
    python coller_tag.py                    # simulation : ce qui serait produit
    python coller_tag.py --apply            # produit tout dans _final/
    python coller_tag.py --apply --only "Dogger"   # un seul jingle, pour ecouter
    python coller_tag.py --apply --gap 0.3         # plus d'air avant le tag
    python coller_tag.py --apply --vhf             # tag filtre facon radio VHF

--vhf applique highpass=300,lowpass=3000 AU TAG : la bande passante d'une
radio maritime. A decider a l'oreille -- l'effet est franc, et il isole le
tag du jingle au lieu de le prolonger.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys

DOSSIER = r"C:\Users\ph.dufourcq\Music\00_AZURACAST\Jingles CH-16"
TAG = "CH16 - On Channel Sixteen.m4a"
SORTIE = "_final"
# Bande passante d'un poste VHF marine, si --vhf est demande.
VHF = "highpass=f=300,lowpass=f=3000"


def ffmpeg_dispo():
    for exe in ("ffmpeg", "ffprobe"):
        if shutil.which(exe) is None:
            sys.exit(f"{exe} introuvable dans le PATH. Installe-le (winget install ffmpeg) "
                     f"puis rouvre le terminal.")


def sonie(path):
    """Sonie integree du fichier, en LUFS (norme EBU R128).

    Mesuree avec ebur128 plutot qu'avec volumedetect : volumedetect donne un
    niveau CRETE, qui dit a quel point le fichier est compresse, pas a quel
    point il s'entend fort. Deux clips au meme pic peuvent sonner a 6 dB
    d'ecart. Retourne None si la mesure echoue -- on collera alors sans
    ajuster plutot que de refuser de travailler.
    """
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", path,
         "-filter_complex", "ebur128=peak=true", "-f", "null", "-"],
        capture_output=True, text=True, errors="replace",
    )
    m = re.findall(r"I:\s*(-?\d+\.?\d*)\s*LUFS", r.stderr)
    return float(m[-1]) if m else None


def coller(jingle, tag, dest, gap, gain_db, vhf, apply_mode):
    """Un seul ffmpeg : silence ajoute au jingle, gain + filtre sur le tag,
    puis concatenation. apad plutot qu'un troisieme flux de silence : c'est le
    jingle qu'on prolonge, le tag n'a pas a porter le blanc."""
    filtre_tag = ["aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo"]
    if abs(gain_db) > 0.1:
        filtre_tag.append(f"volume={gain_db:.1f}dB")
    if vhf:
        filtre_tag.append(VHF)
    chaine = (
        "[0:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
        f"apad=pad_dur={gap}[j];"
        "[1:a]" + ",".join(filtre_tag) + "[t];"
        "[j][t]concat=n=2:v=0:a=1[out]"
    )
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
           "-i", jingle, "-i", tag,
           "-filter_complex", chaine, "-map", "[out]",
           # -map_metadata 0 : artiste/titre poses dans Mp3tag suivent le
           # fichier final, pas besoin de re-tagger les 51.
           "-map_metadata", "0", "-id3v2_version", "3",
           "-c:a", "libmp3lame", "-b:a", "320k", dest]
    if not apply_mode:
        return True, "simulation"
    r = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    return r.returncode == 0, (r.stderr or "").strip()[:200]


def duree(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", path], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dossier", default=DOSSIER)
    ap.add_argument("--tag", default=TAG, help="nom du fichier tag dans le dossier")
    ap.add_argument("--gap", type=float, default=0.15, help="silence avant le tag, en secondes")
    ap.add_argument("--vhf", action="store_true", help="filtre radio VHF sur le tag")
    ap.add_argument("--no-niveau", action="store_true", help="ne pas aligner le niveau du tag")
    ap.add_argument("--only", help="ne traiter que les jingles dont le nom contient ce texte")
    ap.add_argument("--apply", action="store_true", help="produire reellement (sinon simulation)")
    ap.add_argument("--force", action="store_true", help="refaire les fichiers deja produits")
    args = ap.parse_args()

    ffmpeg_dispo()
    tag = os.path.join(args.dossier, args.tag)
    if not os.path.isfile(tag):
        sys.exit(f"Tag introuvable : {tag}")
    sortie = os.path.join(args.dossier, SORTIE)
    os.makedirs(sortie, exist_ok=True)

    jingles = sorted(
        f for f in os.listdir(args.dossier)
        if f.lower().endswith((".m4a", ".mp3", ".wav"))
        and f != args.tag
        and (not args.only or args.only.lower() in f.lower())
    )
    if not jingles:
        sys.exit("Aucun jingle a traiter.")

    sonie_tag = None if args.no_niveau else sonie(tag)
    print(f"Tag : {args.tag} ({duree(tag):.2f} s"
          + (f", {sonie_tag:.1f} LUFS" if sonie_tag is not None else "") + ")")
    print(f"{len(jingles)} jingle(s), silence {args.gap} s"
          + (", tag filtre VHF" if args.vhf else "")
          + ("" if args.apply else "  — SIMULATION") + "\n")

    faits = sautes = echecs = 0
    for f in jingles:
        src = os.path.join(args.dossier, f)
        dest = os.path.join(sortie, os.path.splitext(f)[0] + ".mp3")
        if os.path.exists(dest) and not args.force:
            print(f"  [DEJA] {f}")
            sautes += 1
            continue
        gain = 0.0
        if sonie_tag is not None:
            s = sonie(src)
            if s is not None:
                # Borne a +/-12 dB : au-dela, ce n'est plus un ajustement mais
                # un fichier abime (silence quasi total, ou saturation).
                gain = max(-12.0, min(12.0, s - sonie_tag))
        ok, msg = coller(src, tag, dest, args.gap, gain, args.vhf, args.apply)
        if not ok:
            print(f"  [ECHEC] {f} : {msg}")
            echecs += 1
            continue
        attendu = duree(src) + args.gap + duree(tag)
        reel = duree(dest) if args.apply else attendu
        alerte = "" if abs(reel - attendu) < 0.35 else f"  ⚠ attendu {attendu:.2f} s"
        print(f"  [OK] {f[:46]:<46} {reel:5.2f} s  tag {gain:+.1f} dB{alerte}")
        faits += 1

    print(f"\n{faits} produit(s), {sautes} deja la, {echecs} echec(s) -> {sortie}")
    if not args.apply:
        print("SIMULATION — relance avec --apply pour produire les fichiers.")
    elif faits:
        print("Ecoute le raccord avant d'envoyer : c'est le seul juge.")


if __name__ == "__main__":
    main()
